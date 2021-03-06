import sys, os, subprocess, random
import vars, jwack, state
from helpers import log, log_, relpath, debug2, err, unlink


class BuildError(Exception):
    pass


def _possible_do_files(t):
    yield "%s.do" % t, t, ''
    dirname,filename = os.path.split(t)
    l = filename.split('.')
    l[0] = os.path.join(dirname, l[0])
    for i in range(1,len(l)+1):
        basename = '.'.join(l[:i])
        ext = '.'.join(l[i:])
        if ext: ext = '.' + ext
        yield (os.path.join(dirname, "default%s.do" % ext),
               os.path.join(dirname, basename), ext)


def _find_do_file(t):
    for dofile,basename,ext in _possible_do_files(t):
        debug2('%s: %s ?\n' % (t, dofile))
        if os.path.exists(dofile):
            state.add_dep(t, 'm', dofile)
            return dofile,basename,ext
        else:
            state.add_dep(t, 'c', dofile)
    return None,None,None


def _preexec(t):
    os.environ['REDO_TARGET'] = os.path.basename(t)
    os.environ['REDO_DEPTH'] = vars.DEPTH + '  '
    dn = os.path.dirname(t)
    if dn:
        os.chdir(dn)


def _build(t):
    if (os.path.exists(t) and not state.is_generated(t)
          and not os.path.exists('%s.do' % t)):
        # an existing source file that is not marked as a generated file.
        # This step is mentioned by djb in his notes.  It turns out to be
        # important to prevent infinite recursion.  For example, a rule
        # called default.c.do could be used to try to produce hello.c,
        # which is undesirable since hello.c existed already.
        state.stamp(t)
        return  # success
    state.start(t)
    (dofile, basename, ext) = _find_do_file(t)
    if not dofile:
        raise BuildError('no rule to make %r' % t)
    state.stamp(dofile)
    tmpname = '%s.redo.tmp' % t
    unlink(tmpname)
    f = open(tmpname, 'w+')

    # this will run in the dofile's directory, so use only basenames here
    argv = ['sh', '-e',
            os.path.basename(dofile),
            os.path.basename(basename),  # target name (extension removed)
            ext,  # extension (if any), including leading dot
            os.path.basename(tmpname)  # randomized output file name
            ]
    if vars.VERBOSE:
        argv[1] += 'v'
        log_('\n')
    log('%s\n' % relpath(t, vars.STARTDIR))
    rv = subprocess.call(argv, preexec_fn=lambda: _preexec(t),
                         stdout=f.fileno())
    if rv==0:
        if os.path.exists(tmpname) and os.stat(tmpname).st_size:
            # there's a race condition here, but if the tmpfile disappears
            # at *this* point you deserve to get an error, because you're
            # doing something totally scary.
            os.rename(tmpname, t)
        else:
            unlink(tmpname)
        state.stamp(t)
    else:
        unlink(tmpname)
        state.unstamp(t)
    f.close()
    if rv != 0:
        raise BuildError('%s: exit code %d' % (t,rv))
    if vars.VERBOSE:
        log('%s (done)\n\n' % relpath(t, vars.STARTDIR))


def build(t):
    try:
        return _build(t)
    except BuildError, e:
        err('%s\n' % e)
    return 1


def main(targets, buildfunc):
    retcode = [0]  # a list so that it can be reassigned from done()
    if vars.SHUFFLE:
        random.shuffle(targets)

    locked = []

    def done(t, rv):
        if rv:
            err('%s: exit code was %r\n' % (t, rv))
            retcode[0] = 1

    for i in range(len(targets)):
        t = targets[i]
        if os.path.exists('%s/all.do' % t):
            # t is a directory, but it has a default target
            targets[i] = '%s/all' % t
    
    for t in targets:
        jwack.get_token(t)
        lock = state.Lock(t)
        lock.trylock()
        if not lock.owned:
            log('%s (locked...)\n' % relpath(t, vars.STARTDIR))
            locked.append(t)
        else:
            jwack.start_job(t, lock,
                            lambda: buildfunc(t), lambda t,rv: done(t,rv))
    
    while locked or jwack.running():
        jwack.wait_all()
        if locked:
            t = locked.pop(0)
            lock = state.Lock(t)
            while not lock.owned:
                lock.wait()
                lock.trylock()
            assert(lock.owned)
            relp = relpath(t, vars.STARTDIR)
            log('%s (...unlocked!)\n' % relp)
            if state.stamped(t) == None:
                err('%s: failed in another thread\n' % relp)
                retcode[0] = 2
                lock.unlock()
            else:
                jwack.start_job(t, lock, 
                                lambda: buildfunc(t), lambda t,rv: done(t,rv))
    return retcode[0]
