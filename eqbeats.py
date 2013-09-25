#!/usr/bin/env python
#
# TODO: play-random
# TODO: playlists?

from __future__ import print_function
import sys, os, requests, errno, subprocess, time, json
import pickle, pkg_resources, socket, random, threading
import fcntl, termios, select
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

class ShellPlayerState():
	def __init__(self, track_id):
		self.track = get_track(track_id)
		self.mp3_filename = '%s/%d.mp3' % (eqdir, self.track['id'])
		self.is_cached = os.path.isfile(self.mp3_filename)
		self.duration = get_duration(self.mp3_filename) if self.is_cached else None
		self.info_line = '\033[1;35m%s\033[0m by \033[35m%s\033[0m' % (self.track['title'], self.track['artist']['name'],)
		self.req = None
		self.is_eof = False
		self.received = 0
		self.length = None
		self.buffered = 0
		self.fd = None		
		self.player = None
		self.begin = None
	def terminate(self):
		# Terminate player
		if self.player and not self.player.poll() == 0:
			try:
				self.player.kill()
			except: pass
			self.player = None
		# Delete partial mp3
		if not self.is_cached and not self.is_eof:
			os.remove(self.mp3_filename)
	def try_load_chunk(self):
		if not self.is_cached and not self.is_eof:
			if not self.req:
				# Start downloding if not started yet
				# TODO: try
				self.req = requests.get(self.track['stream']['mp3']) if old_req else requests.get(self.track['stream']['mp3'], stream=True)
				self.fd = open(self.mp3_filename, 'wb')
				self.length = float(self.req.headers.get('content-length'))
			else:
				# Download next data chunk
				buf = self.req.raw.read(8192)
				if buf:
					self.fd.write(buf)
					self.received += len(buf)
					self.buffered = self.received / self.length
				else:
					self.is_eof = True
					self.fd.close()
					self.duration = get_duration(self.mp3_filename)
	def try_run_player(self):
		# TODO: try
		if self.player == None and (self.is_cached or self.is_eof or self.buffered > .15):
			self.player = subprocess.Popen(["mplayer", self.mp3_filename], stdout=FNULL, stderr=subprocess.STDOUT, stdin=FNULL)
			self.begin = time.time()
			return True
		return False
	def is_playing(self):
		return not self.player == None and not self.player.poll() == 0
	def is_buffering(self):
		return not self.req == None and not self.is_cached and not self.is_eof
	def time_played(self):
		return .0 if self.begin == None else time.time() - self.begin
	def part_played(self):
		return .0 if self.duration == None else self.time_played() / self.duration

class ShellPlayer():
	spinner = ('|', '/', '-', '\\')
	state = None
	last_redraw = 0
	ticks = 0
	now_playing = 0
	def __init__(self, queue, x_notify = False, really_play = True):
		self.queue = queue
		self.x_notify = x_notify
		self.really_play = really_play
	def run(self):
		# Put terminal into raw mode
		fd = sys.stdin.fileno()
		oldterm = termios.tcgetattr(fd)
		newattr = termios.tcgetattr(fd)
		newattr[3] = newattr[3] & ~termios.ICANON & ~termios.ECHO
		termios.tcsetattr(fd, termios.TCSANOW, newattr)
		oldflags = fcntl.fcntl(fd, fcntl.F_GETFL)
		fcntl.fcntl(fd, fcntl.F_SETFL, oldflags | os.O_NONBLOCK)
		# Init polling object
		pollobj = select.poll()
		pollobj.register(fd, select.POLLIN)
		# Main loop
		working = True
		played = []
		current_track_id = -1
		while self.now_playing < len(self.queue) and working:
			# Prepare all info about new track to play
			if not self.state:
				current_track_id = self.queue[self.now_playing]
				self.state = ShellPlayerState(current_track_id) # TODO: what if self.state == None?

			# Start or continue downloading (if need)
			self.state.try_load_chunk()

			# If player not started and already have playable file
			if self.really_play:
				is_started = self.state.try_run_player()
				# Notify X user
				if self.x_notify and is_started:
					t = self.state.track
					subprocess.call(['notify-send', 'EqBeats.org', 'New tune #%d by %s' % (t['id'], t['artist']['name'])])

			# Update prompt
			self.redraw_line()

			# Check for user's commands from keyboard
			try:
				ret = pollobj.poll(1000 if not self.state.is_buffering() else 0)
			except:
				continue

			drop_state = False
			if len(ret) > 0:
				chars = sys.stdin.read(10)
				for c in chars:
					if c in ['x', 'X', 'q', 'Q']:
						working = False
					elif c in ['p', 'P']:
						if self.now_playing > 0:
							self.now_playing -= 1
							drop_state = True
					elif c in ['n', 'N']:
						if self.now_playing + 1 < len(self.queue): 
							self.now_playing += 1
							drop_state = True

			# Change track
			if not self.state.is_buffering() and not self.state.is_playing():
				self.now_playing += 1
				drop_state = True
				if not current_track_id in played: played.append(current_track_id)

			# Drop state
			if drop_state or not working:
				self.state.terminate()
				self.state = None

		# Kill player's instance (if any)
		if self.state: self.state.terminate()
		# Return terminal into cooked mode
		termios.tcsetattr(fd, termios.TCSAFLUSH, oldterm)
		fcntl.fcntl(fd, fcntl.F_SETFL, oldflags)
		sys.stdout.write(u'\r\033[K')
		sys.stdout.flush()
		return played

	def redraw_line(self):
		if time.time() - self.last_redraw >= .24 and self.state:
			if self.state.is_playing():
				state_icon = u'\033[32m\u25B6\033[0m'
			else:
				state_icon = u'\033[1;31m'+ self.spinner[self.ticks % len(self.spinner)] + '\033[0m'
				self.ticks += 1

			if self.state.is_buffering():
				percentage = self.state.buffered * 100.0
				tip_line = u'\033[2;30mbuffering %.01f%%\033[0m' % percentage
			else:
				simple_tip_line = u'#%d %d/%d' % (self.state.track['id'], self.now_playing + 1, len(self.queue), )
				bar = int(self.state.part_played() * len(simple_tip_line))
				tip_line = '\033[7m' + simple_tip_line[:bar] + '\033[0m' + simple_tip_line[bar:]

			sys.stdout.write(u'\r  %s  %s [%s]\033[K' % (state_icon, self.state.info_line, tip_line))
			sys.stdout.flush()
			self.last_redraw = time.time()
#	def getWindowSize:
#		import termios, fcntl, struct
#		term_yx = struct.unpack('hh', fcntl.ioctl(0, termios.TIOCGWINSZ, "    "))

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

Keys during playback:
  [N]                 Play next tune from queue
  [P]                 Play previous tune from queue
  [X] or [Q]          Quit player

Report bugs to <igor.bereznyak@gmail.com>.'''
% (sys.argv[0], human_readable(cache_size()), sys.argv[0], sys.argv[0], sys.argv[0], sys.argv[0], sys.argv[0],))
elif command == 'play' and len(arguments) == 0:
	queue = map(lambda x: int(x[x.rfind('/')+1 : x.rfind('.')]), cached_mp3s())
	p = ShellPlayer(queue)
	p.run()
elif command == 'play':
	queue = []
	for arg in arguments:
		if arg.isdigit():  # is it id?
			queue.append(int(arg))
		else:              # is it search query?
			tracks = find_tracks(arg)
			for t in tracks: queue.append(t['id'])

	if (config['shuffle']): random.shuffle(queue)
	p = ShellPlayer(queue)
	p.run()
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
			p = ShellPlayer(queue, config['notify_latest'], config['play_latest'])
			noticed += p.run()
			marshall(noticed, noticed_fname)
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
