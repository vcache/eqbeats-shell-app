#!/usr/bin/env python
#
# TODO: play-random
# TODO: playlists?

from __future__ import print_function
import sys, os, requests, errno, subprocess, time, json
import pickle, pkg_resources, socket, random, threading
from os.path import expanduser

# init

if not __name__ == '__main__': exit(0)
config_default = {
	'check_update' : {
		'comment':
		'How often automatically check for updates:\n# "always": at every run, "on occasion": occasionally, "never": never check',
		'default': '"on occasion"'
	},
	'cache_json'   : {'comment': 'Save EqBeats\'s API output for futher re-using', 'default': 'True'},
	'shuffle'      : {'comment': 'Randomly shuffle playing queue', 'default': 'False'},
	'play_latest'  : {'comment': 'Automatically play latest tracks (for "daemon" command)', 'default': 'True'},
	'notify_latest': {'comment': 'Do an X-Notification about latest tracks (for "daemon" command)', 'default': 'True'},
	'check_period' : {'comment': 'How often to check for a new tracks (in seconds) (for "daemon" command)', 'default': '60 * 15'}}
old_req = pkg_resources.get_distribution("requests").version < '1.0.0'
config = dict()
command = ''
arguments = []
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
	new_cfg = reduce(
		lambda x, y: x + '# ' + config_default[y]['comment'] + '\n' + y + ' = ' + config_default[y]['default']  + '\n\n',
		config_default,
		'# This is eqbeats-shell-app configuration file #\n\n')
	f.write(new_cfg)
	f.close()

# load configuration

try:
	execfile(config_file, dict(), config)
except IOError as e:
	print('Failed to open config file %s: %s' % (config_file, e))
	exit(1)

for c in config_default:
	if not c in config:
		print('Parameter "\033[1;34m%s\033[0m" not specified withing config file (\033[1;34m%s\033[0m), using default value' % (c, config_file))
		config[c] = eval(config_default[c]['default'])

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
		j = i+1
		while j < len(sys.argv):
			arguments.append(sys.argv[j])
			i += 1
			j += 1
	else:
		print ("Unknown command \033[1;31m%s\033[0m" % (sys.argv[i], ))
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
'''
class ShellPlayer():
	spinner = ('|', '/', '-', '\\')
	def __init__(self, queue):	
		self.extplayer = None
		self.percentage = .0
		self.last_redraw = 0
		self.redraw_min_period = .24
		self.ticks = 0
		self.queue = queue
	def run(self):
		now_playing = 0
		track = None
		tty.setraw(sys.stdin.fileno())
		while True:
			if track = None:
				track = get_track(self.queue[now_playing])
				self.percentage = 0
				if self.extplayer: extplayer.kill()
			if not downloaded:
				download chunk and safe to file chunk
				update percentage
			if download done: duration = ...
			if not self.extplayer and (buffered > .15 or downloaded): run extplayer
			self.redraw_line()
			poll for keyinput (timeout = 100 if downloaded else 0)
				process !all! keys
			if ExtPlayer and not ExtPlayer.ISalive(): now_playing++
			if now_playing > queue: break
			if now_playing changed: track = None
		no_cbreaks
	def redraw_line(self):
		if time.time() - self.last_redraw >= self.redraw_min_period:
			sys.stdout.write(u'\r  %s  %s%s\033[K' % (
				u'\033[32m\u25B6\033[0m' if self.extplayer else '\033[1;31m%s\033[0m ' % self.spinner[self.ticks % len(self.spinner)],
				info_line,
				' \033[2;30m(buffering %.01f%%)\033[0m' % self.percentage if self.percentage < 1 else ''))
			sys.stdout.flush()
			self.ticks += 1
			self.last_redraw = time.time()
	def getWindowSize:
		import termios, fcntl, struct
		term_yx = struct.unpack('hh', fcntl.ioctl(0, termios.TIOCGWINSZ, "    "))
'''
def play(n, tip_line):
	spinner = ['|', '/', '-', '\\']
	cached = '%s/%d.mp3' % (eqdir, n['id'])
	info_line = '\033[1;35m%s\033[0m by \033[35m%s\033[0m' % (n['title'], n['artist']['name'],)
	extplayer = None
	if not os.path.isfile(cached):
		verbose("Downloading %s by %s to %s" % (n['title'], n['artist']['name'], cached, ))
		r2 = requests.get(n['stream']['mp3']) if old_req else requests.get(n['stream']['mp3'], stream=True)
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
		else: error("Failed to download %s: %d" % (n['stream']['mp3'], r.status_code, ))
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

def play_queue(queue, notify, really_play, noticed_fname = ''):
	total = len(queue)
	if noticed_fname: noticed = demarshall(noticed_fname)
	for idx, tid in enumerate(queue):
		t = get_track(tid)
		if (t == {} or t == None): continue
		if notify:
			subprocess.call(['notify-send', 'EqBeats.org', 'New tune %d by %s' % (t['id'], t['artist']['name'])])
		if really_play:
			play(t, '#%d %d/%d' % (tid, idx+1, total))
		if noticed_fname:
			noticed.append(tid)
			marshall(noticed, noticed_fname)
	sys.stdout.write('\r\033[K')
	sys.stdout.flush()

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
	print ('''Usage: %s [KEY]... COMMAND [ARGUMENT]...
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
                      when more than 1 arguments provided, will play all of them
  search              search EqBeats
  list                list all tracks uploaded at EqBeats
  cleanup             delete cached mp3-files (currently ~%s)
  complaint           annoyed? write a complaint

Examples:
  %s play 1234 1235 1236
  %s play evdog sci lenich vivix
  %s play "true true friend" zorg scootaloo
  %s search "sim gretina"
  %s complaint "Such a good software"

Report bugs to <igor.bereznyak@gmail.com>.'''
% (sys.argv[0], human_readable(cache_size()), sys.argv[0], sys.argv[0], sys.argv[0], sys.argv[0], sys.argv[0],))
elif command == 'play' and len(arguments) == 0:
	queue = map(lambda x: int(x[x.rfind('/')+1 : x.rfind('.')]), cached_mp3s())
	play_queue(queue, False, True)
elif command == 'play':
	queue = []
	for arg in arguments:
		if arg.isdigit():  # is it id?
			queue.append(int(arg))
		else:              # is it search query?
			tracks = find_tracks(arg)
			for t in tracks: queue.append(t['id'])

	if (config['shuffle']): random.shuffle(queue)
	play_queue(queue, False, True)
elif command == 'search':
	if len(arguments) == 0: verbose("\033[1;35m* (Nothing) *\033[0m")
	for arg in arguments:
		tracks = find_tracks(arg)
		for i in tracks:
			print ('  %d\t\033[1;35m%s\033[0m by \033[35m%s\033[0m @ %s ' % (i['id'], i['title'], i['artist']['name'], i['link'],))
	for arg in arguments:
		users = find_users(arg)
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
			newest = filter(lambda x: not x['id'] in noticed, jsn)
			queue = map(lambda x: x['id'], newest)
			play_queue(queue, config['notify_latest'], config['play_latest'], noticed_fname)
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
	complaint('!mail igor I just try your "eqbeats-shell-app" and here what I think about it: "' + arguments[0] + '". Thats all. Deal with it.')
else:
	error('Unknown command: %s' % (command, ))
	exit(1)
