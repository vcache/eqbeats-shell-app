#!/usr/bin/env python
#
# TODO: playing queue
# TODO: play-random
# TODO: playlists?

from __future__ import print_function
import sys, os, requests, errno, subprocess, time, json
import pickle, pkg_resources, socket, random, threading
from os.path import expanduser

# init

if not __name__ == '__main__': exit(0)
old_req = pkg_resources.get_distribution("requests").version < '1.0.0'
config = dict()
command = ''
argument = ''
eqdir = '%s/.eqbeats' % (expanduser("~"),)
config_file = eqdir + '/.config.py'
verbose = lambda str: True
error = lambda str: print("\033[1;31mERROR\033[0m: %s" % str)
FNULL = open(os.devnull, 'w')
cached_mp3s = lambda : [ eqdir+'/'+f for f in os.listdir(eqdir) if f.endswith(".mp3") ]

# check preconditions

if not os.path.exists(eqdir):
	print('Creating new directory %s' % eqdir)
	os.makedirs(eqdir)

if not os.path.exists(config_file):
	print('Creating default configuration file %s' % config_file)
	f = open(config_file, 'w')
	f.write('''#
# General settings
#

#check_update = 'always'       # Check for updates at every run
check_update = 'on occasion'   # Check for updates occasionally
#check_update = 'never'        # Never check for updates

cache_json = True              # Save EqBeats' API output for futher re-using

#
# Options for the daemonic mode
#

play_latest = True             # Automatically play latest tracks
notify_latest = True           # Do X-Notification about latest tracks
check_period = 60 * 15         # How often check for a new latest (in seconds)''')
	f.close()

# load configuration

try:
	execfile(config_file, dict(), config)
except IOError as e:
	print('Failed to open config file %s: %s' % (config_file, e))
	exit(1)

# check updates

if (config['check_update'] == 'always') or (config['check_update'] == 'on occasion' and random.random() < .2):
	r = requests.get('https://raw.github.com/vcache/eqbeats-shell-app/master/eqbeats.py')
	f = open(sys.argv[0], 'r')
	if not r.text == f.read():
		print('\033[1;31m*\033[0m There is newer version available here: \033[31mhttps://github.com/vcache/eqbeats-shell-app\033[0m \033[1;31m*\033[0m\n')
	f.close()

# parse args

i = 1
while i < len(sys.argv):
	if sys.argv[i] == '--verbose':
		verbose = lambda str: print(str)
	elif sys.argv[i] in ['daemon', 'help', 'list', 'cleanup']:
		command = sys.argv[i]
	elif sys.argv[i] in ['play', 'search', 'complaint']:
		command = sys.argv[i]
		if i+1 < len(sys.argv):
			argument = sys.argv[i+1]
			i = i + 1
	else:
		print ("Unknown argument \033[1;31m%s\033[0m" % (sys.argv[i], ))
		exit(1)
	i = i + 1

# common routines

def demarshall(fname):
	try:
		f = open(fname, 'rb')
		content = pickle.load(f)
		f.close()
	except:
		content = []
	return content

def marshall(data, fname):
	try:
		f = open(fname, 'wb')
		pickle.dump(data, f)
		f.close()
	except e:
		error('Failed to write %s: %s' % (fname, e,))
		return False
	return True

def get_duration(fname):
	out = subprocess.check_output(['mplayer', '-ao', 'null', '-identify', '-frames', '0', fname])
	fields = out.split('\n')
	for f in fields:
		if (f.startswith('ID_LENGTH')):
			k = f.find('=')
			return float(f[k+1:])
	return -1.0

class ExtPlayer(threading.Thread):
	def __init__(self,filename):
		threading.Thread.__init__(self)
		self.daemon = True
		self.filename = filename
		self.play_begin = 0
	def run(self):
		if os.path.exists(self.filename):
			self.play_begin = time.time()
			try:
				subprocess.call(["mplayer", self.filename], stdout=FNULL, stderr=subprocess.STDOUT)
			except OSError as e:
				if e.errno == errno.ENOENT:
					subprocess.call(["mpg123", self.filename], stdout=FNULL, stderr=subprocess.STDOUT)
	def played(self):
		return 0 if self.play_begin == 0 else time.time() - self.play_begin

def play(track_id, tip_line):
	spinner = ['|', '/', '-', '\\']
	cached = '%s/%d.mp3' % (eqdir, track_id, )
	n = get_track(track_id)
	if (n == {} or n == None): return False
	info_line = '\033[1;35m%s\033[0m by \033[35m%s\033[0m' % (n['title'], n['artist']['name'],)
	extplayer = None
	if not os.path.isfile(cached):
		verbose("Downloading %s by %s to %s" % (n['title'], n['artist']['name'], cached, ))
		r2 = requests.get(n['download']['mp3']) if old_req else requests.get(n['download']['mp3'], stream=True)
		if r2.status_code == 200:
			verbose('Saving %s' % (cached, ))
			f = open(cached, 'wb')
			done = 0.0
			total = float(r2.headers.get('content-length'))
			t = 0
			spin = 0
			while True:
				buf = r2.raw.read(8192)
				if not buf: break
				f.write(buf)
				done = done + len(buf)
				if time.time() - t >= .24:
					percentage = done / total * 100.0
					if percentage > 15.0 and extplayer is None:
						extplayer = ExtPlayer(cached)
						extplayer.start()
					if extplayer is None:
						sys.stdout.write( '\r  \033[1;31m%s\033[0m  %s \033[2;30m(buffering %.01f%%)\033[0m\033[K'%(spinner[spin % len(spinner)], info_line, percentage,))
					else:
						sys.stdout.write(u'\r  \033[32m\u25B6\033[0m  %s \033[2;30m(buffering %.01f%%)\033[0m\033[K'%(info_line, percentage,))
					sys.stdout.flush()
					spin += 1
					t = time.time()
			f.close()
		else: error("Failed to download %s: %d" % (n['download']['mp3'], r.status_code, ))
	else: verbose("Playing cached version %s" % (cached,))

	duration = get_duration(cached)
	if extplayer is None:
		extplayer = ExtPlayer(cached)
		extplayer.start()

	while extplayer.isAlive():
		bar = int((extplayer.played() / duration) * len(tip_line))
		rich_tip_line = '\033[7m' + tip_line[:bar] + '\033[0m' + tip_line[bar:]
		sys.stdout.write(u'\r  \033[1;32m\u25B6\033[0m  %s \033[2;30m[%s]\033[0m\033[K' % (info_line, rich_tip_line,))
		sys.stdout.flush()
		time.sleep(1)

	sys.stdout.write(u'\r     %s \033[2;30m[%s]\033[0m\033[K' % (info_line, tip_line))
	sys.stdout.flush()
	return True

def complaint(msg):
	s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	s.connect(('irc.ponychat.net', 6667))
	s.send('NICK angryuser\r\n')
	time.sleep(1)
	s.send('USER angryuser angryuser irc.poynchat.net :User of eqbeats-shell-app\r\n')
	time.sleep(1)
	s.send('NICK angryuser\r\n')
	time.sleep(1)
	s.send('JOIN #eqbeats\r\n')
	time.sleep(1)
	s.send('PRIVMSG #eqbeats :%s\r\n' % (msg, ))
	time.sleep(1)
	s.send('QUIT :Just a angry user complaints on eqbeats-shell-app\r\n')
	s.close()
	return True

def get_user(uid):
	r = requests.get('https://eqbeats.org/user/%d/json' % uid)
	if r.status_code != 200:
		error('Failed to fetch user info')
		return {}
	return r.json if old_req else r.json()

def find_users(query):
	r = requests.get('https://eqbeats.org/users/search/json?q=%s' % query)
	if r.status_code != 200:
		error('Failed to find users info')
		return []
	return r.json if old_req else r.json()

def get_track(tid):
	cached_json = '%s/%d.json' % (eqdir, tid)
	if config['cache_json'] and os.path.exists(cached_json):
		f = open(cached_json, 'r')
		jsn = f.read()
		f.close()
	else:
		r = requests.get('https://eqbeats.org/track/%d/json' % tid)
		if r.status_code != 200:
			error('Failed to fetch track info')
			return {}
		jsn = r.text
		if config['cache_json']:
			try:
				f = open(cached_json, 'w')
				f.write(jsn)
				f.close()
			except:
				error('Failed to save JSON cached for #%d' % tid)
	return json.loads(jsn)

def find_tracks(query):
	r =  requests.get('https://eqbeats.org/tracks/search/json?q=%s' % query)
	if r.status_code != 200:
		error('Failed to find tracks info')
		return []
	jsn = r.json if old_req else r.json()
	tracks_into_cache(jsn)
	return jsn

def tracks_into_cache(tracks):
	for t in tracks:
		cached_json = '%s/%d.json' % (eqdir, t['id'])
		if (os.path.exists(cached_json)): continue
		try:
			f = open(cached_json, "w")
			f.write(json.dumps(t))
			f.close()
		except:
			error("Failed to save JSON cached for #%d" % t['id'])

def cache_size(): return reduce(lambda x, y: x + os.stat(y).st_size, cached_mp3s(), 0)

def human_readable(num): # by Fred Cirera
    for x in ['bytes','KB','MB','GB','TB']:
        if num < 1024.0:
            return "%3.1f %s" % (num, x)
        num /= 1024.0
	
# execute the command

if command == 'help' or command == '':
	print ('''Usage: %s [KEY]... COMMAND [ARGUMENT]
EqBeats command line tool.

Keys:
  --verbose           be verbose

Commands:
  help                print this message and exit
  daemon              start workin in background command
  play                play music(if any), argument may be:
                        - none, play all cached tracks
                        - numerical id, play track with a give ID
                        - text string, play all tracks matching text
                      when more than 1 arguments provided, will play all of them (TODO)
  search              search EqBeats
  list                list all tracks uploaded at EqBeats
  cleanup             delete cached mp3-files (currently ~%s)
  complaint           annoyed? write a complaint

Examples:
  %s play 1234
  %s play evdog
  %s play "true true friend"
  %s search "sim gretina"
  %s complaint "Such a good software"

Report bugs to <igor.bereznyak@gmail.com>.'''
% (sys.argv[0], human_readable(cache_size()), sys.argv[0], sys.argv[0], sys.argv[0], sys.argv[0], sys.argv[0],))
elif command == 'play' and argument == '':
	tracks = cached_mp3s()
	for (idx, fname) in enumerate(tracks):
		tid = int(fname[fname.rfind('/')+1:fname.rfind('.')])
		play(tid, '#%d %d/%d' % (tid, idx+1, len(tracks)) )

elif command == 'play':
	played = False

	# is it id?
	if argument.isdigit():
		tid = int(argument)
		played = play(tid, '#%d 1/1' % tid)

	# is it artist?
#	if not played:
#		r = requests.get('https://eqbeats.org/users/search/json?q=%s' % (argument, ))
#		if r.status_code == 200:
#			jsn = r.json if old_req else r.json()
#			for artist in jsn:
#				for track in artist['tracks']:
#					played = played or play(track['id'])

	# is it tracks?
	if not played:
		tracks = find_tracks(argument)
		verbose('Going to play this stuff: ')
		for i in tracks:
			verbose('  %d\t\033[1;35m%s\033[0m by \033[35m%s\033[0m @ %s ' % (i['id'], i['title'], i['artist']['name'], i['link'],))
		for idx, track in enumerate(tracks):
			play(track['id'], '#%d %d/%d' % (track['id'], idx+1, len(tracks)) )
	
	sys.stdout.write('\r\033[K')
	sys.stdout.flush()
elif command == 'search':
	verbose("Tracks matching \"%s\": " % (argument, ))
	tracks = find_tracks(argument)
	if len(tracks) == 0: verbose("\033[1;35m* (Nothing) *\033[0m")
	for i in tracks:
		print ('  %d\t\033[1;35m%s\033[0m by \033[35m%s\033[0m @ %s ' % (i['id'], i['title'], i['artist']['name'], i['link'],))
	users = find_users(argument)
	verbose("Users matching \"%s\": " % (argument, ))
	for i in users: print ('  \033[35m%s\033[0m: %s' % (i['name'], i['link'],))
elif command == 'daemon':
	verbose('Working as a daemon')
	if not config['notify_latest'] and not config['play_latest']:
		error("Please select --play-latest or --notify-latest or both")
		exit(1)
	noticed_fname = '%s/.noticed' % (eqdir, )
	# TODO: check that only one daemon running
	while True:
		r = requests.get('https://eqbeats.org/tracks/latest/json')
		if r.status_code == 200:
			noticed = demarshall(noticed_fname)
			jsn = r.json if old_req else r.json()
			tracks_into_cache(jsn)
			new_cnt = reduce(lambda x, y: x + (1 if not y['id'] in noticed else 0), jsn, 0)
			new_shown = 1
			for i in jsn:
				if not i['id'] in noticed:
					verbose('New track %s\t\033[1;35m%s\033[0m by \033[35m%s\033[0m' %(i['id'], i['title'], i['artist']['name'],))
					if config['notify_latest']:
						subprocess.call(['notify-send', 'EqBeats.org', 'New tune %d by %s' % (i['id'], i['artist']['name'],)])
					if config['play_latest']: play(i['id'], '#%d %d/%d' % (i['id'], new_shown, new_cnt))
					noticed.append(i['id'])
					marshall(noticed, noticed_fname)
					new_shown+=1
		time.sleep(config['check_period'])
		# TODO: substract froms sleep time already spent
elif command == 'list':
	r = requests.get('https://eqbeats.org/tracks/all/json')
	if r.status_code == 200:
		jsn = r.json if old_req else r.json()
		tracks_into_cache(jsn)
		for i in jsn:
			qwe = '  %d\t\033[1;35m%s\033[0m by \033[35m%s\033[0m @ %s ' % (i['id'], i['title'], i['artist']['name'], i['link'])
			print(qwe.encode('utf-8').strip())
	else:
		error('Failed to fetch list')
elif command == 'cleanup':
	victims = cached_mp3s()
	if len(victims) > 0:
		print('Following files will be deleted: %s' % (reduce(lambda x, y: x + '\n  ' + y, victims, ''),))
		print('Total: \033[1;31m' + human_readable(cache_size()) + '\033[0m\n')
		for i in range(5):
			print('Press Ctrl+C to cancel \033[1;31m%d\033[0m' % (4-i,))
			time.sleep(1)
		for i in victims: os.remove(i)
elif command == 'complaint':
	complaint('!mail igor I just try your "eqbeats-shell-app" and here what I think about it: "' + argument + '". Thats all. Deal with it.')
else:
	error('Unknown command: %s' % (command, ))
	exit(1)
