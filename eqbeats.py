#!/usr/bin/env python
#
# TODO: playing queue
# TODO: play-cached, play-random, play "some string", play "username"
# TODO: show-track, show-user
# TODO: playlists?

from __future__ import print_function
import sys, os, requests, errno, subprocess, time, pickle, pkg_resources, socket
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
	elif sys.argv[i] in ['daemon', 'help', 'xs', 'list', 'cleanup']:
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

def marshall(fname):
	try:
		f = open(fname, 'rb')
		content = pickle.load(f)
		f.close()
	except:
		content = []
	return content

def demarshall(data, fname):
	try:
		f = open(fname, 'wb')
		pickle.dump(data, f)
		f.close()
	except e:
		error('Failed to write %s: %s' % (fname, e,))
		return False
	return True

def play(track_id):
	if track_id == '' or not track_id.isdigit():
		error('You didn\'t specify track id')
		return False
	cached = '%s/%s.mp3' % (eqdir, track_id, )
	if not os.path.isfile(cached):
		r = requests.get('https://eqbeats.org/track/%s/json' % (track_id,))
		n = r.json if old_req else r.json()
		if r.status_code == 200:
			verbose("Downloading %s by %s to %s" % (n['title'], n['artist']['name'], cached, ))
			r2 = requests.get(n['download']['mp3'])
			if r2.status_code == 200:
				verbose('Saving %s' % (cached, ))
				try:
					f = open(cached, 'wb')
					while True:
						buffer = r2.raw.read(8192)
						if not buffer: break
						f.write(buffer)
					f.close()
				except e: error('Failed to save file: %s' % e)
			else: error("Failed to download %s: %d" % (n['download']['mp3'], r.status_code, ))
		else: error("Failed to request: %d" % (r.status_code, ))
	else: verbose("Playing cached version %s" % (cached,))
	try:
		subprocess.call(["mplayer", cached], stdout=None if is_verbose else FNULL, stderr=subprocess.STDOUT)
	except OSError as e:
		if e.errno == errno.ENOENT:
			try:
				subprocess.call(["mpg123", cached], stdout=None if is_verbose else FNULL, stderr=subprocess.STDOUT)
			except OSError as e2:
				if e2.errno == errno.ENOENT:
					subprocess.call(["ffplay", cached], stdout=None if is_verbose else FNULL, stderr=subprocess.STDOUT)
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
  play                download and play track (specify track's id as an argument)
  search              search EqBeats
  xs                  search EqBeats for currently selected text
  show-user           show user info (specify user's id as an argument)
  show-track          show track info (specify track's id as an argument)a
  list                list all tracks uploaded at EqBeats
  cleanup             delete cached files
  complaint           annoyed? write a complaint

Examples:
  %s --verbose play 1234
  %s play-random
  %s play-cached
  %s play evdog
  %s play "true true friend"
  %s search "sim gretina"
  %s --play-latest --notify-latest daemon
  %s complaint "Such a good software"

Report bugs to <igor.bereznyak@gmail.com>.'''
% (sys.argv[0], sys.argv[0], sys.argv[0], sys.argv[0], sys.argv[0], sys.argv[0], sys.argv[0], sys.argv[0], sys.argv[0],))
elif command == 'play':
	if not play(argument): exit(1)
elif command == 'search' or command == 'xs':
	if command == 'xs':
		try:
			argument = subprocess.check_output(['xsel', '-o'])
		except:
			exit(1)
	verbose("Tracks matching \"%s\": " % (argument, ))
	r = requests.get('https://eqbeats.org/tracks/search/json?q=%s' % (argument,))
	if r.status_code == 200:
		jsn = r.json if old_req else r.json()
		if len(jsn) == 0: verbose("\033[1;35m* (Nothing) *\033[0m")
		for i in jsn:
			print ('  %d\t\033[1;35m%s\033[0m by \033[35m%s\033[0m @ %s ' % (i['id'], i['title'], i['artist']['name'], i['link'],))
	r = requests.get('https://eqbeats.org/users/search/json?q=%s' % (argument,))
	if r.status_code == 200:
		results = r.json if old_req else r.json()
		if len(results) > 0:
			verbose("Users matching \"%s\": " % (argument, ))
			for i in results: print ('  \033[35m%s\033[0m: %s' % (i['name'], i['link'],))
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
			noticed = marshall(noticed_fname)
			jsn = r.json if old_req else r.json()
			for i in jsn:
				if not i['id'] in noticed:
					verbose('New track %s\t\033[1;35m%s\033[0m by \033[35m%s\033[0m' %(i['id'], i['title'], i['artist']['name'],))
					if notify_latest: subprocess.call(['notify-send', 'EqBeats.org', 'New tune %d by %s' % (i['id'], i['artist']['name'],)])
					if play_latest: play(str(i['id']))
					noticed.append(i['id'])
					demarshall(noticed, noticed_fname)
		time.sleep(check_period)
		# TODO: substract froms sleep time already spended
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
	complaint('igor: I just try your "eqbeats-shell-app" and what I think about it "' + argument + '". Thats all. Deal with it.')
else:
	error('Unknown command: %s' % (command, ))
	exit(1)
