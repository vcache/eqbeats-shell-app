#!/usr/bin/env python
#
# TODO: add tasks
# TODO: play-cached, play-random, play "some string", play "username"
# TODO: show-track, show-user
# TODO: playlists?

from __future__ import print_function
import sys, os, requests, errno, subprocess, time, pickle
from os.path import expanduser

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
	elif sys.argv[i] == 'play' or sys.argv[i] == 'search':
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

def play(track_id):
	if track_id == '' or not track_id.isdigit():
		error('You didn\'t specify track id')
		return False
	cached = '%s/%s.mp3' % (eqdir, track_id, )
	if not os.path.isfile(cached):
		r = requests.get('https://eqbeats.org/track/%s/json' % (track_id,))
		n = r.json
		if r.status_code == 200:
			verbose("Downloading %s by %s to %s" % (n['title'], n['artist']['name'], cached, ))
			r2 = requests.get(n['download']['mp3'])
			if r2.status_code == 200:
				verbose('Saving %s' % (cached, ))
				f = open(cached, 'wb')
				while True:
					buffer = r2.raw.read(8192)
					if not buffer: break
					f.write(buffer)
				f.close
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

Examples:
  %s --verbose play 1234
  %s play-random
  %s play-cached
  %s play evdog
  %s play "true true friend"
  %s search "sim gretina"
  %s --play-latest --notify-latest daemon

Report bugs to <igor.bereznyak@gmail.com>.'''
% (sys.argv[0], sys.argv[0], sys.argv[0], sys.argv[0], sys.argv[0], sys.argv[0], sys.argv[0], sys.argv[0], ))
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
		results = r.json
		if len(results) > 0:
			for i in results:
				print ('  %d\t\033[1;35m%s\033[0m by \033[35m%s\033[0m @ %s ' % (i['id'], i['title'], i['artist']['name'], i['link'],))
		else:
			verbose("\033[1;35m* (Nothing) *\033[0m")
	r = requests.get('https://eqbeats.org/users/search/json?q=%s' % (argument,))
	if r.status_code == 200:
		results = r.json
		if len(results) > 0:
			verbose("Users matching \"%s\": " % (argument, ))
			for i in results: print ('  \033[35m%s\033[0m: %s' % (i['name'], i['link'],))
elif command == 'daemon':
	verbose('Working as a daemon')
	# TODO: check that only one daemon running
	while True:
		r = requests.get('https://eqbeats.org/tracks/latest/json')
		if r.status_code == 200:
			# get noticed
			try:
				f = open('%s/.noticed' % eqdir, 'rb')
				noticed = pickle.load(f)
				f.close()
			except:
				noticed = []
			# check for new
			for i in r.json:
				if not i['id'] in noticed:
					verbose('New track %s\t\033[1;35m%s\033[0m by \033[35m%s\033[0m' %(i['id'], i['title'], i['artist']['name'],))
					if notify_latest:
						subprocess.call(['notify-send', 'EqBeats.org', 'New tune #%s by %s' % (i['id'], i['artist']['name'],)])
					if play_latest:
						play(str(i['id']))
					noticed.append(i['id'])
			# dump noticed
			try:
				f = open('%s/.noticed' % eqdir, 'wb')
				pickle.dump(noticed, f)
				f.close()
			except e:
				error('Failed to write noticed: %s' % e)
		time.sleep(check_period)
		# TODO: substract froms sleep time spended for 'check for new'
elif command == 'list':
	r = requests.get('https://eqbeats.org/tracks/all/json')
	if r.status_code == 200:
		for i in r.json:
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
else:
	error('Unknown command: %s' % (command, ))
	exit(1)
