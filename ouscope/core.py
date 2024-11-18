"""The telescope control is provided through the `Telescope` class which provides state tracking and low level methods - forming a basic API layer. The higher level functions are implemented as separate functions construced with the Telescope class API."""

# AUTOGENERATED! DO NOT EDIT! File to edit: ../10_core.ipynb.

# %% ../10_core.ipynb 2
from __future__ import annotations

# %% auto 0
__all__ = ['Telescope']

# %% ../10_core.ipynb 3
from fastcore.basics import patch

import logging
import requests
from requests import session

import configparser
import diskcache
from bs4 import BeautifulSoup
import json
import time, datetime
import os, tempfile, shutil, sys
from os import path
from os.path import expanduser

from zipfile import ZipFile, BadZipFile
from io import StringIO, BytesIO
from tqdm.auto import tqdm

# %% ../10_core.ipynb 4
def cleanup(s: str) -> str:
    '''
    Remove non-asci characters from the string.
    '''
    return s.encode('ascii','ignore').decode('ascii','ignore')

# %% ../10_core.ipynb 6
class Telescope:
    '''
    Main telescope website API class.
    '''
    
    url='https://www.telescope.org/'
    cameratypes={
        'constellation':'1',
        'galaxy':       '2',
        'cluster':      '3',
        'planet':'5',
        'coast':'6',
        'pirate':'7',
    }

    REQUESTSTATUS_TEXTS={
        1: "New",
        2: "New, allocated",
        3: "Waiting",
        4: "In progress",
        5: "Reallocate",
        6: "Waiting again",
        7: "Complete on site",
        8: "Complete",
        9: "Hold",
        10: "Frozen",
        20: "Expired",
        21: "Expired w/CJobs",
        22: "Cancelled",
        23: "Cancelled w/CJobs",
        24: "Invalid",
        25: "Never rises",
        26: "Other error",
    }
    
    def __init__(self, user='', passwd='', config=None, cache='.cache/jobs'):
        if config is not None:
            conf = configparser.ConfigParser()
            conf.read(expanduser(config))
            self.user = conf['telescope.org']['user']
            self.passwd = conf['telescope.org']['password']
            self.cache = conf['cache']['jobs']
        elif user and passwd :
            self.user=user
            self.passwd=passwd
            self.cache=cache
        else :
            print('WARNING: You need to provide user&password or config file!')
            print('WARNING: This object is not going to work!')
            return
            
        self.s=None
        self.tout=60
        self.retry=15
        self.login()


# %% ../10_core.ipynb 7
@patch
def login(self: Telescope):
    '''
    Login into the telescope site using credentials initialised in the constructor.
    Start and store persistent session with the website.
    '''
    log = logging.getLogger(__name__)
    payload = {'action': 'login',
               'username': self.user,
               'password': self.passwd,
               'stayloggedin': 'true'}
    log.debug('Get session ...')
    self.s=session()
    log.debug('Logging in ...')
    self.s.post(self.url+'login.php', data=payload)

# %% ../10_core.ipynb 8
@patch
def logout(self: Telescope):
    '''
    Logout and close the session. The stored session data are removed.  
    '''
    if self.s is None :
        self.s.post(self.url+'logout.php')
        self.s=None

# %% ../10_core.ipynb 13
@patch
def __do_api_call(self: Telescope, module, req, params=None):
    rq = self.s.post(self.url+"api-user.php", {'module': module,
                                               'request': req,
                                               'params': {} if params is None else json.dumps(params)})
    return json.loads(rq.content)

#| exporti
@patch
def __do_rm_api(self: Telescope, req, params=None):
    return self.__do_api_call("request-manager", req, params)


#| exporti
@patch
def __do_rc_api(self: Telescope, req, params=None):
    return self.__do_api_call("request-constructor", req, params)

# %% ../10_core.ipynb 14
@patch
def get_user_requests(self: Telescope, 
                      folder: int =1,    # Id of the listed folder. Inbox=1.
                      sort : str ='rid', # Name of the sorting colum: 'rid', 'object' or 'completion'
                      ) -> list(dict):   # List of dictionaries representing the requests.
    '''
    Get all user requests from folder (Inbox=1 by default),
    sorted by sort column ('rid' by default). 
    Possible sort columns are: 'rid', 'object', 'completion'
    The data is returned as a list of dictionaries.
    '''

    #fetch first batch        
    params={
        'limit': 100,
        'sort': sort,
        'folderid': folder}

    dat = self.__do_rm_api("1-get-list-own", params)
    res=[]
    total=int(dat['data']['totalRequests'])
    res+=dat['data']['requests']

    # Fetch the rest
    params['limit']=total-len(res)
    params['startAfterRow']=len(res)
    dat = self.__do_rm_api("1-get-list-own", params)

    total=int(dat['data']['totalRequests'])
    res+=dat['data']['requests']
    return res

# %% ../10_core.ipynb 16
@patch
def get_jid_for_req(self:Telescope, req=None) -> int:
    '''
    Find and output jobID for the request.
    If request is not yet done returns False.

    ### Input
    
    req : request dictionary or requestid

    ### Output

    JobID if the request is completed, otherwise False
    '''
    if req is not None:
        try: 
            id = req['id']
            if req['status'] != '8':
                return None
        except TypeError:
            id = req
            
    rq = self.s.post(self.url+"v4request-view.php?" + f'rid={id}')
    soup = BeautifulSoup(rq.text,'lxml')
    
    for blk in soup.find_all('script'):
        if "var info = " in blk.text:
            for l in  blk.text.split('\n'):
                if "var info = " in l:
                    l = l[l.find('{'):l.rfind('}')+1]
                    return json.loads(l)['jid']
    return None

# %% ../10_core.ipynb 18
@patch
def get_user_folders(self: Telescope):
    '''
    Get all user folders. Returns list of dictionaries.
    '''
    return self.__do_rm_api("0-get-my-folders")['data']

# %% ../10_core.ipynb 20
@patch
def get_obs_list(self: Telescope, t=None, dt=1, filtertype='', camera='', hour=16, minute=0, verb=False):
    '''Get the dt days of observations taken no later then time in t.

        ### Input
        
        t  - end time in seconds from the epoch
            (as returned by time.time())
        dt - number of days, default to 1
        filtertype - filter by type of filter used
        camera - filter by the camera/telescope used

        ### Output
        
        Returns a list of JobIDs (int) for the observations.

    '''

    assert(self.s is not None)

    if t is None :
        t=time.time()-time.timezone


    st=time.gmtime(t-86400*dt)
    et=time.gmtime(t)

    d=st.tm_mday
    m=st.tm_mon
    y=st.tm_year
    de=et.tm_mday
    me=et.tm_mon
    ye=et.tm_year

    log = logging.getLogger(__name__)
    log.debug('%d/%d/%d -> %d/%d/%d', d,m,y,de,me,ye)

    try :
        telescope=self.cameratypes[camera.lower()]
    except KeyError:
        telescope=''

    searchdat = {
        'sort1':'completetime',
        'sort1order':'desc',
        'searchearliestcom[]':[d, m, y, str(hour),str(minute)],
        'searchlatestcom[]':  [de,me,ye,str(hour),str(minute)],
        'searchstatus[]':['1'],
        'resultsperpage':'1000',
        'searchfilter':filtertype,
        'searchtelescope':telescope,
        'submit':'Go'
    }

    headers = {'Content-Type': 'application/x-www-form-urlencoded'}


    request = self.s.post(self.url+'v3job-search-query.php',
                     data=searchdat, headers=headers)
    soup = BeautifulSoup(request.text,'lxml')

    if verb:
        for h in soup.findAll('h3'):
            if 'Parameters' in h.text:
                print('Params:')
                for l in h.find_next_sibling().get_text(strip=True, separator='\n').splitlines():
                    print(l)
            elif 'Results' in h.text:
                p = h.find_next_sibling()
                if 'jobs' in p.text:
                    print('Results:')
                    for l in h.find_next_sibling().get_text(strip=True, separator='\n').splitlines():
                        print(l)
    
    jlst=[]
    for l in soup.findAll('tr'):
        try :
            a=l.find('a').get('href')
        except AttributeError :
            continue
        jid=a.rfind('jid')
        if jid>0 :
            jid=a[jid+4:].split('&')[0]
            jlst.append(int(jid))
    return jlst

# %% ../10_core.ipynb 22
@patch
def get_job(self: Telescope, jid=None):
    '''Get a job data for a given JID'''

    assert(jid is not None)
    assert(self.s is not None)

    log = logging.getLogger(__name__)
    log.debug(jid)

    obs={}
    obs['jid']=jid
    # rq=self.s.post(self.url+('v3cjob-view.php?jid=%d' % jid))
    rq=self.s.post(self.url+('v4request-view.php?jid=%d' % jid))
    soup = BeautifulSoup(rq.text, 'lxml')
    for l in soup.findAll('tr'):
        log.debug(cleanup(l.text))
        txt=''
        for f in l.findAll('td'):
            if txt.find('Request ID') >= 0:
                obs['rid']=f.text[1:]            
            if txt.find('Object Type') >= 0:
                obs['type']=f.text
            if txt.find('Object ID') >= 0:
                obs['oid']=f.text
            if txt.find('Telescope Type Name') >= 0:
                obs['tele']=f.text
            if txt.find('Filter Type') >= 0:
                obs['filter']=f.text
            if txt.find('Exposure Time') >= 0:
                obs['exp']=f.text
            if txt.find('Completion Time') >= 0:
                t=f.text.split()
                obs['completion']=t[3:6]+[t[6][1:]]+[t[7][:-1]]
            if txt.find('Status') >= 0:
                obs['status']= (f.text == 'Success')

            txt=f.text
    for l in soup.findAll('button'):
        if l.get('onclick')is not None and ('dl-flat' in l.get('onclick')):
            obs['flatid']=int(l.get('onclick').split('=')[-1][:-1])
            break
    log.info('%(jid)d [%(tele)s, %(filter)s, %(status)s]: %(type)s %(oid)s %(exp)s', obs)

    return obs

# %% ../10_core.ipynb 25
@patch
def get_request(self: Telescope, rid=None):
    '''Get request data for a given RID'''

    assert(rid is not None)
    assert(self.s is not None)

    log = logging.getLogger(__name__)
    log.debug(rid)

    obs={}
    obs['rid']=rid
    #rq=self.s.post(self.url+('v3cjob-view.php?jid=%d' % jid))
    rq=self.s.post(self.url+('v4request-view.php?rid=%d' % rid))
    soup = BeautifulSoup(rq.text, 'lxml')
    for l in soup.findAll('tr'):
        log.debug(cleanup(l.text))
        txt=''
        for f in l.findAll('td'):
            if txt.find('Job ID') >= 0:
                obs['jid']=f.text[1:]
            if txt.find('Object Type') >= 0:
                obs['type']=f.text
            if txt.find('Object ID') >= 0:
                obs['oid']=f.text
            if txt.find('Object Name') >= 0:
                obs['name']=f.text
            if txt.find('Telescope Type Name') >= 0:
                obs['tele_type']=f.text
            if txt.find('Telescope Name') >= 0:
                obs['tele']=f.text
            if txt.find('Filter Type') >= 0:
                obs['filter']=f.text
            if txt.find('Dark Frame') >= 0:
                obs['dark']=f.text
            if txt.find('Exposure Time') >= 0:
                obs['exp']=f.text
            if txt.find('Request Time') >= 0:
                t=f.text.split()
                obs['requested']=t[3:6]+[t[6][1:]]+[t[7][:-1]]
            if txt.find('Completion Time') >= 0:
                t=f.text.split()
                obs['completion']=t[3:6]+[t[6][1:]]+[t[7][:-1]]
            if txt.find('Status') >= 0:
                obs['status']= f.text.strip() #(f.text == 'Success')

            txt=f.text
    for l in soup.findAll('a'):
        if l.get('href')is not None and ('dl-flat' in l.get('href')):
            obs['flatid']=int(l.get('href').split('=')[1])
            break
    log.info('%(jid)d [%(tele)s, %(filter)s, %(status)s]: %(type)s %(oid)s %(exp)s', obs)

    return obs    

# %% ../10_core.ipynb 27
@patch
def download_obs(self: Telescope, obs=None, directory='.', cube=True, pbar=False, verbose=False):
    '''Download the raw observation obs (obtained from get_job) into zip
    file named job_jid.zip located in the directory (current by default).
    Alternatively, when the cube=True the file will be a 3D fits file.
    The name of the file (without directory) is returned.'''

    assert(obs is not None)
    assert(self.s is not None)

    chunksize = 1024
    tq = None

    payload = {'jid': obs['jid']}
    if 'flatid' in obs :
        payload['flatid']=obs['flatid']
    
    rsp = self.__do_api_call("image-engine", 
                             "0-create-dl" + ("3d" if cube else "zip"), payload)
    ieid = rsp['data']['ieID']

    n=0    
    while rsp['status']!='READY' :
        if verbose:
            print(f"{rsp['status']:30}", end='\n')
        time.sleep(2)
        n+=1
        rsp = self.__do_api_call("image-engine", "0-is-job-ready", {'ieid':ieid,})
        if n>30:
            raise TimeoutError
    
    if verbose:
        print(f"{rsp['status']:30}")
        sys.stdout.flush()
    
    rq=self.s.get(self.url+f'v3image-download.php?jid={obs["jid"]}&ieid={ieid}', 
                  stream=True)
    
    size = int(rq.headers.get('Content-Length', 0))
    fn = ('%(jid)d.' % obs) + ('fits' if cube else 'zip')
    siz = int(rsp['data']['fitssize' if cube else 'fitsbzsize'])
    if pbar :
        tq = tqdm(desc=fn,       
                  total=size,       
                  unit="B",       
                  unit_scale=True,        
                  leave=True,       
                  miniters=1)

    with open(os.path.join(directory, fn), 'wb') as fd:
        for chunk in rq.iter_content(chunksize):
            if chunk:
                fd.write(chunk)
                if tq :
                    tq.update(len(chunk))
    if tq :
        tq.close()
    sys.stdout.flush()
    if siz==os.stat(os.path.join(directory, fn)).st_size :
        return fn
    else:
        return None

# %% ../10_core.ipynb 29
@patch
def get_obs(self: Telescope, obs=None, cube=True, recurse=True, pbar=False, verbose=False):
    '''Get the raw observation obs (obtained from get_job) into zip
    file-like object. The function returns ZipFile structure of the
    downloaded data.'''

    assert(obs is not None)
    assert(self.s is not None)

    log = logging.getLogger(__name__)

    fn = ('%(jid)d.' % obs) + ('fits' if cube else 'zip')
    fp = path.join(self.cache,fn[0],fn[1],fn)
    if not path.isfile(fp) :
        log.info('Getting %s from server', fp)
        os.makedirs(path.dirname(fp), exist_ok=True)
        self.download_obs(obs,path.dirname(fp),cube=cube,pbar=pbar,verbose=verbose)
    else :
        log.info('Getting %s from cache', fp)
    content = open(fp,'rb')
    try :
        return content if cube else ZipFile(content)
    except BadZipFile :
        # Probably corrupted download. Try again once.
        content.close()
        os.remove(fp)
        if recurse :
            return self.get_obs(obs, cube, False)
        else :
            return None


# %% ../10_core.ipynb 32
@patch
def download_obs_processed(self: Telescope, obs=None, directory='.', cube=False, pbar=False):
    '''Download the raw observation obs (obtained from get_job) into zip
    file named job_jid.zip located in the directory (current by default).
    Alternatively, when the cube=True the file will be a 3D fits file.
    The name of the file (without directory) is returned.'''

    assert(obs is not None)
    assert(self.s is not None)

    log = logging.getLogger(__name__)

    fn=None

    tout=self.tout
    tq = None
    chunksize = 1024
 
    while tout > 0 :
        rq=self.s.get(self.url+
                      ('imageengine-request.php?jid=%d&type=%d' %
                        (obs['jid'], 1 if cube else 3 )))

        soup = BeautifulSoup(rq.text, 'lxml')
        dlif=soup.find('iframe')

        try :
            dl=dlif.get('src')
            rq=self.s.get(self.url+dl,stream=True)
            size = int(rq.headers.get('Content-Length', 0))
            fn = ('art_%(jid)d.' % obs) + ('fits' if cube else 'zip')

            if pbar :
                tq = tqdm(desc=fn,       
                          total=size,       
                          unit="B",       
                          unit_scale=True,        
                          leave=True,       
                          miniters=1)

            with open(path.join(directory, fn), 'wb') as fd:
                for chunk in rq.iter_content(chunksize):
                    fd.write(chunk)
                    if tq :
                        tq.update(len(chunk))
                    
            if tq: 
                tq.close()
            return fn
        except AttributeError :
            tout-=self.retry
            log.warning('No data. Sleep for %ds ...'%self.retry)
            time.sleep(self.retry)

    return None



# %% ../10_core.ipynb 34
@patch
def get_obs_processed(self: Telescope, obs=None, cube=False):
    '''Get the raw observation obs (obtained from get_job) into zip
    file-like object. The function returns ZipFile structure of the
    downloaded data.'''

    assert(obs is not None)
    assert(self.s is not None)
    log = logging.getLogger(__name__)

    tout=self.tout
       
    while tout > 0 :
        rq=self.s.get(self.url+
                      ('imageengine-request.php?jid=%d&type=%d' %
                        (obs['jid'], 1 if cube else 3 )))

        soup = BeautifulSoup(rq.text,'lxml')
        dlif=soup.find('iframe')
        try :
            dl=dlif.get('src')
            rq=self.s.get(self.url+dl,stream=True)
            return BytesIO(rq.content) if cube else ZipFile(BytesIO(rq.content))

        except AttributeError :
            tout-=self.retry
            log.warning('No data. Sleep for %ds ...'%self.retry)
            time.sleep(self.retry)

    return None


# %% ../10_core.ipynb 38
@patch
def submit_job_api(self: Telescope, obj, exposure=30000, tele='COAST',
                    filt='BVR', darkframe=True,
                    name='RaDec object', comment='AutoSubmit'):
    assert(self.s is not None)

    log = logging.getLogger(__name__)

    ra=obj.ra.to_string(unit='hour', sep=':', pad=True, precision=2,
                        alwayssign=False)
    dec=obj.dec.to_string(sep=':', pad=True, precision=2,
                        alwayssign=True)
    try :
        tele=self.cameratypes[tele.lower()]
    except KeyError :
        log.warning('Wrong telescope: %d ; selecting COAST(6)', tele)
        tele=6

    if tele==7 :
        if filt=='BVR' : filt='Colour'
        if filt=='B' : filt='Blue'
        if filt=='V' : filt='Green'
        if filt=='R' : filt='Red'
    if tele==6 :
        if filt=='Colour' : filt='BVR'
        if filt=='Blue' : filt='B'
        if filt=='Green' : filt='V'
        if filt=='Red' : filt='R'

    params = {'telescopeid': tele, 'telescopetype': 2,
              'exposuretime': exposure, 'filtertype': filt,
              'objecttype': 'RADEC', 'objectname': name,
              'objectid': ra+' '+dec, 'usercomments': comment }

    self.__do_rc_api("0-rb-clear")

    r = self.__do_rc_api("0-rb-set", params)
    log.debug('Req data:%s', r)
    if r['success'] :
        r = self.__do_rc_api("0-rb-submit")
        log.debug('Submission data:%s', r)
    if r['success'] :
        return True, r['data']['id']
    else :
        log.warning('Submission error. Status:%s', r['status'])
        return False, r['status']

# %% ../10_core.ipynb 39
@patch
def submit_RADEC_job(self: Telescope, obj, exposure=30000, tele='COAST',
                    filt='BVR', darkframe=True,
                    name='RaDec object', comment='AutoSubmit'):
    assert(self.s is not None)

    log = logging.getLogger(__name__)

    ra=obj.ra.to_string(unit='hour', sep=' ',
                        pad=True, precision=2,
                        alwayssign=False).split()
    dec=obj.dec.to_string(sep=' ',
                        pad=True, precision=2,
                        alwayssign=True).split()
    try :
        tele=self.cameratypes[tele.lower()]
    except KeyError :
        log.warning('Wrong telescope: %d ; selecting COAST(6)', tele)
        tele=6

    if tele==7 :
        if filt=='BVR' : filt='Colour'
        if filt=='B' : filt='Blue'
        if filt=='V' : filt='Green'
        if filt=='R' : filt='Red'
    if tele==6 :
        if filt=='Colour' : filt='BVR'
        if filt=='Blue' : filt='B'
        if filt=='Green' : filt='V'
        if filt=='Red' : filt='R'

    u=self.url+'/request-constructor.php'
    r=self.s.get(u+'?action=new')
    t=self.extract_ticket(r)
    log.debug('GoTo Part 1 (ticket %s)', t)
    r=self.s.post(u,data={'ticket':t,'action':'main-go-part1'})
    t=self.extract_ticket(r)
    log.debug('GoTo RADEC (ticket %s)', t)
    r=self.s.post(u,data={'ticket':t,'action':'part1-go-radec'})
    t=self.extract_ticket(r)
    log.debug('Save RADEC (ticket %s)', t)
    r=self.s.post(u,data={'ticket':t,'action':'part1-radec-save',
                         'raHours':ra[0],
                         'raMins':ra[1],
                         'raSecs':ra[2].split('.')[0],
                         'raFract':ra[2].split('.')[1],
                         'decDegrees':dec[0],
                         'decMins':dec[1],
                         'decSecs':dec[2].split('.')[0],
                         'decFract':dec[2].split('.')[1],
                         'newObjectName':name})
    t=self.extract_ticket(r)
    log.debug('GoTo Part 2 (ticket %s)', t)
    r=self.s.post(u,data={'ticket':t,'action':'main-go-part2'})
    t=self.extract_ticket(r)
    log.debug('Save Telescope (ticket %s)', t)
    r=self.s.post(u,data={'ticket':t,
                            'action':'part2-save',
                            'submittype':'Save',
                            'newTelescopeSelection':tele})
    t=self.extract_ticket(r)
    log.debug('GoTo Part 3 (ticket %s)', t)
    r=self.s.post(u,data={'ticket':t,'action':'main-go-part3'})
    t=self.extract_ticket(r)
    log.debug('Save Exposure (ticket %s)', t)
    r=self.s.post(u,data={'ticket':t,
                            'action':'part3-save',
                            'submittype':'Save',
                            'newExposureTime':exposure,
                            'newDarkFrame': 1 if darkframe else 0,
                            'newFilterSelection':filt,
                            'newRequestComments':comment})
    t=self.extract_ticket(r)
    log.debug('Submit (ticket %s)', t)
    r=self.s.post(u,data={'ticket':t, 'action':'main-submit'})
    return r
