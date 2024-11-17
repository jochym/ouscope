"""Image processing submodule."""

# AUTOGENERATED! DO NOT EDIT! File to edit: ../30_process.ipynb.

# %% auto 0
__all__ = ['verts', 'codes', 'marker', 'plot_sequence', 'process_job', 'analyse_job']

# %% ../30_process.ipynb 4
import configparser
from fastcore.basics import patch
from os.path import expanduser
from ouscope.core import Telescope
from ouscope.solver import Solver

from IPython import display

import time
from datetime import datetime
import os
from requests import session
from bs4 import BeautifulSoup
from io import StringIO, BytesIO
from zipfile import ZipFile
from astropy.io import fits
from astropy.coordinates import SkyCoord, Longitude, Latitude
import astropy.units as u
from astropy.wcs import WCS
from astropy.io import fits
from astropy.visualization import simple_norm
from astroquery.vizier import Vizier
from tqdm.auto import tqdm
import matplotlib as mpl
from matplotlib import pyplot as plt
from matplotlib.path import Path
import numpy as np
from photutils.detection import DAOStarFinder
from astropy.stats import sigma_clipped_stats
from numpy import argsort
from sqlitedict import SqliteDict

from astropy.visualization import make_lupton_rgb

import astroalign as aa
from collections import namedtuple
from ouscope.vs import get_VS_sequence

# %% ../30_process.ipynb 5
plt.rcParams['image.cmap'] = 'gray'

# %% ../30_process.ipynb 13
def make_color_image(layers, black=1.0, Q=5, stretch=200, mults=(0.95, 1.0, 1.0), order='BVR'):

    seq = argsort(list(order))
    b, r, g = (m*layers[l] for m,l in zip(mults,seq))
    # print([order[i] for i in seq])
    
    try :
        r_r, r_f = aa.register(r, g, detection_sigma=10)
    except TypeError:
        r_r = r
        
    try :
        b_r, b_f = aa.register(b, g, detection_sigma=10)
    except TypeError:
        b_r = b
        
    minlev = np.array([sigma_clipped_stats(l, sigma=3.0)[1] for l in (r,g,b)])
    return make_lupton_rgb(0.9*r_r, g, b_r, minimum=black*minlev, Q=Q, stretch=stretch)

# %% ../30_process.ipynb 14
verts = [
    (0, 0.5),
    (0.3, 0.5),
    (0.7, 0.5),
    (1, 0.5),
]
verts = verts + [(y, x) for x, y in verts]
verts = [(y-0.5, x-0.5) for x, y in verts]
codes = 4*[Path.MOVETO, Path.LINETO]
marker = Path(verts, codes)

# %% ../30_process.ipynb 15
def plot_sequence(vs):
    if vs in VSdb:
        seq = VSdb[vs]['seq']
        if not seq[0]:
            return
    ax = plt.gca()
    ax.text(0, 0, seq[0], color='C1')
    for s in seq[1]:
        print(s)
        dx = 20/3600
        ax.plot(s[3], s[5], marker=marker, lw=1, color='C2', ms=30, transform=ax.get_transform('world'))
        ax.text(s[3]+dx, s[5]-dx, s[1], color='white', transform=ax.get_transform('world'))

# %% ../30_process.ipynb 16
def process_job(jid, reprocess=False, cls=True, layer=None):
    job = OSO.get_job(jid)
    ctime = job['completion']
    req = OSO.get_request(int(job['rid'].split()[0]))
    target = req['name'].lstrip().rstrip()
    print(f'jid {jid}: ({target})')
    print(f'{" ".join(ctime)}')
    z = OSO.get_obs(job, cube=False, verbose=False)    
    hdul=[fits.open(BytesIO(z.read(name)))[0] for name in z.namelist()]
    if layer is not None:
        hdul=[hdul[layer]]
    # hdul = fits.open(OSO.get_obs(job, cube=True, verbose=False))
    print(f'Filters: {tuple(hdu.header["FILTER"] for hdu in hdul)}')
    if not reprocess and jid in DB :
        print('Done')
        if cls:
            display.clear_output(wait=True);
        return
    hi = min(1, len(hdul)-1)
    # hi = 0
    for hdu in hdul:
        wcs_head = solver.solve(hdu, tout=30)
        if wcs_head:
            break
    if not wcs_head:
        print('Cannot solve image')
        OSO.get_obs(job, cube=True, verbose=False)
        data = hdul[hi].data[:-32,:-32]
        plt.imshow(data, norm=simple_norm(data, 'asinh', asinh_a=0.01))
        plt.show();
        return
    w = WCS(wcs_head)
    box = w.calc_footprint()
    c = box.mean(axis=0)
    s = box.max(axis=0) - box.min(axis=0)
    result = Vizier.query_region(catalog='B/gcvs', 
                                 coordinates=SkyCoord(*c, unit='deg', frame='fk5'), 
                                 width=f'{s[0]}deg', height=f'{s[1]}deg')
#     for g in result:
#         for n, o in enumerate(g):
#             if 'Name' in o.keys():
#                 name = o['Name']
#             elif 'GCVS' in o.keys():
#                 name = ' '.join(o['GCVS'].split())
#             elif 'NSV' in o.keys():
#                 name = f'NSV_{o["NSV"]}'

#             print(f'{name:12} {o["magMax"]:6.2f}', o)
    ax = plt.subplot(projection=w)
    plt.grid(color='white', ls='solid')
    for g in result:
        print(g)
        for n, o in enumerate(g):
            if 'Name' in o.keys():
                name = o['Name']
            elif 'GCVS' in o.keys():
                name = ' '.join(o['GCVS'].split())
            elif 'NSV' in o.keys():
                name = f'NSV_{o["NSV"]}'
            else :
                name = f'VS_{n}'
            if name.startswith('V0'):
                name = 'V'+name[2:]
            if name in VSdb:
                jobl = VSdb[name]
            else :
                jobl = {}
                jobl['jobs']=set()
            jobl['jobs'] |= {jid}
            VSdb[name]=jobl
            try :
                frame='icrs'
                try :
                    radec = SkyCoord(o['RAJ2000'] + o['DEJ2000'], 
                                     frame=frame, unit=(u.hourangle, u.deg))
                except ValueError:
                    radec = SkyCoord(o['RAJ2000'], o['DEJ2000'], 
                                     frame=frame, unit=(u.deg, u.deg))                    
            except KeyError:
                    radec =  SkyCoord(o['_RA.icrs'] + o['_DE.icrs'], 
                                     frame='icrs', unit=(u.hourangle, u.deg))
                    frame='icrs'
#                     radec =  SkyCoord(o['RAB1950'] + o['DEB1950'], 
#                                      frame='fk4', unit=(u.hourangle, u.deg))
            ax.plot(radec.ra.deg, radec.dec.deg, marker=marker, color='C1', ms=30,
                    transform=ax.get_transform('world'), )#edgecolor='yellow', facecolor='none')
            ax.text(radec.ra.deg+0.012, radec.dec.deg-0.012, f'{name} ({o["magMax"]:.1f})', 
                    transform=ax.get_transform('world'), color='white')
            if name.lstrip().rstrip().lower() == target.lower():
                plot_sequence(target)
                
    if cls :
        display.clear_output(wait=True)
        print(f'jid {jid}: ({target})')
        print(f'{" ".join(ctime)}')
        print(f'Filters: {tuple(hdu.header["FILTER"] for hdu in hdul)}')

    try :
        if len(hdul)==3:
            plt.imshow(make_color_image([hdu.data[:-32,:-32] for hdu in hdul], order=tuple(hdu.header["FILTER"] for hdu in hdul)))
        else :
            data = hdul[hi].data[:-32,:-32]
            plt.imshow(data, norm=simple_norm(data, 'asinh', asinh_a=0.01))
    except aa.MaxIterError:
        data = hdul[hi].data[:-32,:-32]
        plt.imshow(data, norm=simple_norm(data, 'asinh', asinh_a=0.01))
    DB[jid]=Job(jid, [int(rid[1:]) for rid in job['rid'].split()], True)
    plt.show()
    display.display(plt.gcf());    

# %% ../30_process.ipynb 17
def analyse_job(jid, rid=None, reprocess=False):
    job = OSO.get_job(jid)
    ctime = job['completion']
    if rid is None:
        rid=int(job['rid'].split()[0])
    req = OSO.get_request(rid)
    target = req['name'].lstrip().rstrip()
    print(f'J{jid}:R{rid} ({target}) {" ".join(ctime)}')
    z = OSO.get_obs(job, cube=False, verbose=False)
    hdul=[fits.open(BytesIO(z.read(name)))[0] for name in z.namelist()]
    print(f'Filters: {" ".join(hdu.header["FILTER"] for hdu in hdul)}')
    if not reprocess and jid in DB:
        print('Done')
        return
    hi = min(1, len(hdul)-1)
    # hi = 0
    for hdu in hdul:
        wcs_head = solver.solve(hdu, tout=30)
        if wcs_head:
            break
    if not wcs_head:
        print('Cannot solve image')
        OSO.get_obs(job, cube=True, verbose=False)
        return
    w = WCS(wcs_head)
    box = w.calc_footprint()
    c = box.mean(axis=0)
    s = box.max(axis=0) - box.min(axis=0)
    result = Vizier.query_region(catalog='B/gcvs', 
                                 coordinates=SkyCoord(*c, unit='deg', frame='fk5'), 
                                 width=f'{s[0]}deg', height=f'{s[1]}deg')
    for g in result:
        for n, o in enumerate(g):
            if 'Name' in o.keys():
                name = o['Name']
            elif 'GCVS' in o.keys():
                name = ' '.join(o['GCVS'].split())
            elif 'NSV' in o.keys():
                name = f'NSV_{o["NSV"]}'
            else :
                name = f'VS_{n}'
            if name.startswith('V0'):
                name = 'V'+name[2:]
            if name in VSdb:
                jobl = VSdb[name]
            else :
                jobl = {}
                jobl['jobs']=set()
                jobl['seq']=None
            try :
                jobl['jobs'] |= {jid}
            except TypeError:
                jobl['jobs'] = {jid}
            if not jobl['seq']:
                try :
                    seq = get_VS_sequence(name, 40, 16)
                except ConnectionError:
                    time.sleep(5)
                    seq = get_VS_sequence(name, 40, 16)
                if seq[0] and seq[1]:
                    jobl['seq']=seq
            VSdb[name]=jobl
            print(f'{name}', end=" ")
            if jobl["seq"] and jobl["seq"][0] and jobl["seq"][1]:
                print(f'seq:{jobl["seq"][0]} ({len(jobl["seq"][1])})')
            else :
                print()                      
    DB[jid]=Job(jid, [int(rid[1:]) for rid in job['rid'].split()], True)
    return True
