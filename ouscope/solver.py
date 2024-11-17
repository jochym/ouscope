"""Field solver module - thin layer over other field solver services."""

# AUTOGENERATED! DO NOT EDIT! File to edit: ../15_solver.ipynb.

# %% auto 0
__all__ = ['Solver']

# %% ../15_solver.ipynb 3
import configparser
import logging
from fastcore.basics import patch
from os.path import expanduser
import os, tempfile, shutil
from io import StringIO, BytesIO
from astroquery.exceptions import TimeoutError as ASTTimeoutError
from astropy.time import Time
from astropy.io import fits
from astropy.coordinates import SkyCoord, Longitude, Latitude
from astropy.wcs import WCS
from .core import Telescope
import ouscope.util as ousutil

# %% ../15_solver.ipynb 4
class Solver:
    '''
    Wrapper of AstrometryNet solver from astropy tuned for the use in osob use.
    '''
    
    _cmd = 'solve-field'
    _args = '-p -l %d -O -L %d -H %d -u app -3 %f -4 %f -5 2 %s'
    _telescopes={
        'galaxy':   (1,2),
        'cluster':  (14,16),
        'coast': (1, 2),
        'pirate': (1, 2),
        '10micron': (1, 2),
        'cdk17': (1, 2),
        'unknown': (1,16),
        'undefined': (1,16),
        "'undefined'": (1,16),
    }

    
    def __init__(self, api_key=None, cache='.cache/wcs', cmd=None, args=None):
        if cmd is None:
            self._cmd = Solver._cmd
        else:
            self._cmd = cmd
        if args is None:
            self._args = Solver._args
        else:
            self._args = args
        self._cmd = ' '.join((self._cmd, self._args))
        self.ast = None
        self.api_key = api_key
        if api_key:
            from astroquery.astrometry_net import AstrometryNet
            self.ast = AstrometryNet()    
            self.ast.api_key = api_key
        self._cache = cache
        self._tout = 15

# %% ../15_solver.ipynb 5
@patch
def solve(self: Solver, hdu, crop=(slice(0,-32), slice(0,-32)), force_solve=False, tout=None):
    '''
    Solve plate in fits format using local (if present) or 
    remote (not fully implemented yet) AstrometryNet solver
    '''
    loger = logging.getLogger(__name__)
    if hdu.verify_datasum()!=1:
        hdu.add_datasum()
    fn = f'{int(hdu.header["DATASUM"]):08X}.wcs'
    fp = os.path.join(self._cache,fn[0],fn[1],fn)
    if force_solve or not os.path.isfile(fp) :
        loger.info(f'Solving for {fn[:-4]}')
        print(f'Solving for {fn[:-4]}')
        s = self._solveField_local(hdu, tout=tout)
        if s:
            wcs_header = fits.Header(s.header)
            #wcs_header['NAXIS'] = 2
            #wcs_header['NAXIS1'] = wcs_header['IMAGEW']
            #wcs_header['NAXIS2'] = wcs_header['IMAGEH']
            os.makedirs(os.path.dirname(fp), exist_ok=True)
            with open(fp, 'w') as fh:
                wcs_header.totextfile(fp)
        else:
            wcs_header = None
    else :
        loger.info(f'Getting {fn[:-4]} from cache')
        print(f'Getting {fn[:-4]} from cache')
        with open(fp, 'r') as fh:
            wcs_header = fits.Header.fromtextfile(fh)        
    return wcs_header

# %% ../15_solver.ipynb 6
@patch
def _getFrameRaDec(self: Solver, hdu):
    if 'OBJCTRA' in hdu.header:
        ra=hdu.header['OBJCTRA']
        dec=hdu.header['OBJCTDEC']
    elif 'MNTRA' in hdu.header :
        ra=hdu.header['MNTRA']
        dec=hdu.header['MNTDEC']
    elif 'RA-TEL' in hdu.header :
        ra=hdu.header['RA-TEL']
        dec=hdu.header['DEC-TEL']
    else :
        raise KeyError

    try :
        eq=Time(hdu.header['EQUINOX'], format='decimalyear')
    except KeyError :
        eq=Time(2000, format='decimalyear')

    o=SkyCoord(Longitude(ra, unit='hour'),
               Latitude(dec, unit='deg'),
               frame='icrs', obstime=hdu.header['DATE-OBS'],
               equinox=eq)
    return o


# %% ../15_solver.ipynb 7
@patch
def _solveField_local(self: Solver, hdu, tout=None, cleanup=True):
    '''
    Run local solver for hdu.
    '''
    loger = logging.getLogger(__name__)
    o=self._getFrameRaDec(hdu)
    ra=o.ra.deg
    dec=o.dec.deg

    try :
        tel = hdu.header['TELESCOP'].lower()
    except KeyError:
        tel = 'unknown'
        hdu.header.remove('TELESCOP')
        hdu.header['TELESCOP'] = tel

    if hdu.header['TELESCOP']=="'undefined'":
        tel = 'unknown'
        hdu.header.remove('TELESCOP')
        hdu.header['TELESCOP'] = tel        
        
    if 'brt' in tel:
        tel=tel.split()[1]
    else :
        tel=tel.split()[0]

    loapp, hiapp=Solver._telescopes[tel]
    td=tempfile.mkdtemp(prefix='field-solver')
    try :
        fn=tempfile.mkstemp(dir=td, suffix='.fits')
        loger.debug(td, fn)
        #print(fn[1], hdu.header['TELESCOP'])
        hdu.writeto(fn[1])
        cmd = self._cmd % (self._tout if tout is None else tout,
                           loapp, hiapp, ra, dec, fn[1])
        loger.debug(cmd)
        print(cmd)
        solver=os.popen(cmd)
        for ln in solver:
            loger.debug(ln.strip())
        shdu=fits.open(BytesIO(open(fn[1][:-5]+'.new','rb').read()))
        return shdu[0]
    except IOError :
        return None
    finally :
        if cleanup :
            shutil.rmtree(td)

