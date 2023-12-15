#!/usr/bin/env python3
# coding: utf-8

import ouscope
from ouscope.core import Telescope
from ouscope.vs import submitVarStar
from collections import namedtuple
import configparser
import os
import logging
from os.path import expanduser

import argparse

parser = argparse.ArgumentParser()
parser.add_argument('-s', '--submit', help='Execute the submission', action='store_true')
parser.add_argument('-q', '--quiet', help='Jast do the job. Stay quiet', action='store_true')
parser.add_argument('-v', '--verbose', help='Print more status info', action='store_true')
parser.add_argument('-d', '--debug', help='Print debugging info', action='store_true')
args = parser.parse_args()

if args.verbose :
    logging.basicConfig(level=os.environ.get("LOGLEVEL", "INFO"))
if args.debug :
    logging.basicConfig(level=os.environ.get("LOGLEVEL", "DEBUG"))

log = logging.getLogger(__name__)

VStar=namedtuple('VStar', 'name comm expos')

config = configparser.ConfigParser()
config.read(expanduser('~/.config/telescope.ini'))

log.info('Log in to telescope.org ...')

scope=Telescope(config['telescope.org']['user'], config['telescope.org']['password'])
# BRT.astrometryAPIkey=config['astrometry.net']['apikey']

def qprint(*ar, **kwar):
    if not args.quiet:
        print(*ar, **kwar)

def vprint(*ar, **kwar):
    if args.verbose and not args.quiet:
        print(*ar, **kwar)


obslst=[
    #VStar('S Ori', comm='Mira AAVSO', expos=120),
    VStar('V1223 Sgr', comm='AAVSO', expos=180),
    VStar('CH Cyg', comm='Symbiotic AAVSO', expos=60),
    VStar('SS Cyg', comm='Mira', expos=180),
    #VStar('EU Cyg', comm='Mira', expos=180),
    VStar('IP Cyg', comm='Mira', expos=180),
    VStar('V686 Cyg', comm='Mira', expos=180),
    #VStar('AS Lac', comm='Mira', expos=120),
    VStar('BI Her', comm='Mira', expos=180),
    VStar('DX Vul', comm='Mira', expos=180),
    VStar('DQ Vul', comm='Mira', expos=180),
    VStar('EQ Lyr', comm='Mira', expos=180),
    VStar('LX Cyg', comm='AAVSO', expos=180),
    ]


log.info('Getting observing queue ...')

reqlst=scope.get_user_requests(sort='completion')
q=[r for r in reqlst if int(r['status'])<8]
qn=[r['objectname'] for r in q]
missing = [vs for vs in obslst if vs.name not in qn]

vprint("Queue:")
for j in qn:
    vprint(j)

if missing :
    if args.submit:
        qprint('Submitting missing jobs:')
    else:
        qprint('Dry run. Add -s to the command line to do actual submissions.')
        
    for vs in missing:
        qprint(f'{vs.name.split()[0]:>8} {vs.name.split()[1]} exp:{vs.expos:3.1f}s   {vs.comm}', end='')
        if args.submit :
            r, i = scope.submitVarStar(vs.name, expos=vs.expos, comm=vs.comm)
            if r :
                qprint(f' => id: {i}', end='')
            else :
                qprint(f' Failure:{i}', end='')
        qprint()
else :
    qprint('No missing jobs. Nothing to do!')

log.info('Done.')
