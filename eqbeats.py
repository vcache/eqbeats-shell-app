#!/usr/bin/env python
#
# TODO: playing queue
# TODO: play-random
# TODO: playlists?

from __future__ import print_function
import sys, os, requests, errno, subprocess, time, pickle, pkg_resources, socket, random, threading
from os.path import expanduser

old_req = pkg_resources.get_distribution("requests").version < '1.0.0'

# init

if not __name__ == '__main__': exit(0)

play_latest = False
notify_latest = False
command = ''
argument = ''
eqdir = '%s/.eqbeats' % (expanduser("~"),)
check_period = 60*15

verbose = lambda str: True
is_verbose = False
error = lambda str: print("\033[1;31mERROR\033[0m: %s" % str)

FNULL = open(os.devnull, 'w')

# check updates

if random.random() < .2:
	r = requests.get('https://raw.github.com/vcache/eqbeats-shell-app/master/eqbeats.py')
	f = open(sys.argv[0], 'r')
	if not r.text == f.read():
		print('\033[1;31m*\033[0m There is newer version available here: \033[31mhttps://github.com/vcache/eqbeats-shell-app\033[0m \033[1;31m*\033[0m\n')
	f.close()

# parse args

i = 1
while i < len(sys.argv):
	if sys.argv[i] == '--play-latest':
		play_latest = True
	elif sys.argv[i] == '--notify-latest':
		notify_latest = True
	elif sys.argv[i] == '--verbose':
		verbose = lambda str: print(str)
		is_verbose = True
	elif sys.argv[i].startswith('--check-period'):
		k = sys.argv[i].find('=')
		check_period = 60 * int((sys.argv[i])[k+1:])
	elif sys.argv[i] in ['daemon', 'help', 'list', 'cleanup']:
		command = sys.argv[i]
	elif sys.argv[i] in ['play', 'search', 'complaint']:
		command = sys.argv[i]
		argument = sys.argv[i+1]
		i = i + 1
	else:
		print ("Unknown argument \033[1;31m%s\033[0m" % (sys.argv[i], ))
		exit(1)
	i = i + 1

# check preconditions

if not os.path.exists(eqdir):
	verbose('Creating new directory %s' % (eqdir, ))
	os.makedirs(eqdir)

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
	r = requests.get('https://eqbeats.org/track/%d/json' % (track_id,))
	n = r.json if old_req else r.json()
	info_line = '\033[1;35m%s\033[0m by \033[35m%s\033[0m' % (n['title'], n['artist']['name'],)
	extplayer = None
	if not os.path.isfile(cached):
		if r.status_code == 200:
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
		else: error("Failed to request: %d" % (r.status_code, ))
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
	r = requests.get('https://eqbeats.org/track/%d/json' % tid)
	if r.status_code != 200:
		error('Failed to fetch track info')
		return {}
	return r.json if old_req else r.json()

def find_tracks(query):
	r =  requests.get('https://eqbeats.org/tracks/search/json?q=%s' % query)
	if r.status_code != 200:
		error('Failed to find tracks info')
		return []
	return r.json if old_req else r.json()
	
# execute the command

if command == 'help' or command == '':
	print ('''Usage: %s [KEY]... COMMAND [ARGUMENT]
EqBeats command line tool.

Keys:
  --verbose           be verbose
  --play-latest       download and play latest tracks (while in daemon)
  --notify-latest     do X-notifications on latest tracks (while in daemon)
  --check-period      how often do checks while daemon (in minutes)

Commands:
  help                print this message and exit
  daemon              start workin in background command
  play                play music(if any), argument may be:
                        - none, play all cached tracks (TODO)
                        - numerical id, play track with a give ID
                        - text string, play all tracks matching text
                      when more than 1 arguments provided, will play all of them (TODO)
  search              search EqBeats
  list                list all tracks uploaded at EqBeats
  cleanup             delete cached files
  complaint           annoyed? write a complaint

Examples:
  %s play 1234
  %s play evdog
  %s play "true true friend"
  %s search "sim gretina"
  %s --play-latest --notify-latest daemon
  %s complaint "Such a good software"

Report bugs to <igor.bereznyak@gmail.com>.'''
% (sys.argv[0], sys.argv[0], sys.argv[0], sys.argv[0], sys.argv[0], sys.argv[0], sys.argv[0],))
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
		for idx, track in enumerate(tracks): play(track['id'], '#%d %d/%d' % (i['id'], idx+1, len(tracks)) )
	
	print("")		
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
	if not notify_latest and not play_latest:
		error("Please select --play-latest or --notify-latest or both")
		exit(1)
	noticed_fname = '%s/.noticed' % (eqdir, )
	# TODO: check that only one daemon running
	while True:
		r = requests.get('https://eqbeats.org/tracks/latest/json')
		if r.status_code == 200:
			noticed = demarshall(noticed_fname)
			jsn = r.json if old_req else r.json()
			for i in jsn:
				if not i['id'] in noticed:
					verbose('New track %s\t\033[1;35m%s\033[0m by \033[35m%s\033[0m' %(i['id'], i['title'], i['artist']['name'],))
					if notify_latest: subprocess.call(['notify-send', 'EqBeats.org', 'New tune %d by %s' % (i['id'], i['artist']['name'],)])
					if play_latest: play(i['id'], '-')
					noticed.append(i['id'])
					marshall(noticed, noticed_fname)
		time.sleep(check_period)
		# TODO: substract froms sleep time already spent
elif command == 'list':
	r = requests.get('https://eqbeats.org/tracks/all/json')
	if r.status_code == 200:
		jsn = r.json if old_req else r.json()
		for i in jsn:
			print ('  %d\t\033[1;35m%s\033[0m by \033[35m%s\033[0m @ %s ' % (i['id'], i['title'], i['artist']['name'], i['link'],))
	else:
		error('Failed to fetch list')
elif command == 'cleanup':
	victims = [ eqdir+'/'+f for f in os.listdir(eqdir) if f.endswith(".mp3") ]
	if len(victims) > 0:
		print('Following files will be deleted: %s' % (reduce(lambda x, y: x + '\n  ' + y, victims, ''),))
		for i in range(5):
			print('Press Ctrl+C to cancel \033[1;31m%d\033[0m' % (4-i,))
			time.sleep(1)
		for i in victims: os.remove(i)
elif command == 'complaint':
	complaint('!mail igor I just try your "eqbeats-shell-app" and here what I think about it: "' + argument + '". Thats all. Deal with it.')
else:
	error('Unknown command: %s' % (command, ))
	exit(1)
