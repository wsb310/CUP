#!/usr/bin/env python
# -*- coding: utf-8 -*
# Copyright: [CUP] - See LICENSE for details.
# Authors: Guannan Ma (@mythmgn), Zhao Minghao, Zhange Yuetian
"""
:descrition:
    shell related module
"""

import os
import time
import sys
import shutil
import signal
import random
import hashlib
import warnings
import datetime
import threading
import traceback
import subprocess
import collections

import cup
from cup import err
# from cup.res import linux
from cup.shell import expect

__all__ = [
    'md5file',
    'kill9_byname',
    'del_if_exist',
    'execshell',
    'execshell_withpipe',
    'expect',
    'execshell_withpipe_exwitherr',
    'is_proc_alive',
    'forkexe_shell',
    'execshell_withpipe_ex',
    'execshell_withpipe_str',
    'ShellExec',
    'rmtree',
    'Asynccontent'
]

_DEPRECATED_MSG = '''Plz use class cup.shell.ShellExec instead. Function %s
 deprecated'''


class Asynccontent(object):
    """
    make a Argcontent to async_run u have to del it after using it
    """
    def __init__(self):
        self.cmd = None
        self.timeout = None
        self.pid = None
        self.ret = None
        self.child_list = []
        self.__cmdthd = None
        self.__monitorthd = None
        self.__subpro = None


class ShellExec(object):  # pylint: disable=R0903
    """
    用来执行shell的类。 用法如下:
    from cup import shell
    shellexec = shell.ShellExec()
    # timeout=None, 一直等待直到命令执行完
    shellexec.run('/bin/ls', timeout=None)
    # timeout>=0, 等待固定时间，如超时未结束terminate这个shell命令。
    shellexec.run(cmd='/bin/ls', timeout=100)
    """

    def __init__(self):
        self._subpro = None
        self._subpro_data = None

    def __kill_process(self, pid):
        os.kill(pid, signal.SIGKILL)

    def kill_all_process(self, async_content):
        """
        to kill all process
        """
        for pid in async_content.child_list:
            self.__kill_process(pid)

    def get_async_run_status(self, async_content):
        """
        get the command's status
        """
        try:
            from cup.res import linux
            async_process = linux.Process(async_content.pid)
            res = async_process.get_process_status()
        except err.NoSuchProcess:
            res = "process is destructor"
        return res

    def get_async_run_res(self, async_content):
        """
        if the process is still running the res shoule be None,None,0
        """
        return async_content.ret

    def async_run(self, cmd, timeout):
        """
        async_run
        return a dict {uuid:pid}
        self.argcontent{cmd,timeout,ret,cmdthd,montor}
        timeout:returncode:999
        cmd is running returncode:-999
        """

        def _signal_handle():
            """
            signal setup
            """
            signal.signal(signal.SIGPIPE, signal.SIG_DFL)

        def _target(argcontent):
            argcontent.__subpro = subprocess.Popen(
                    argcontent.cmd, shell=True, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    preexec_fn=_signal_handle)

            #parent = psutil.Process(argcontent.__subpro.pid)
            from cup.res import linux
            parent = linux.Process(argcontent.__subpro.pid)
            children = parent.children(True)
            ret_dict = []
            for process in children:
                #ret_dict.append(process.pid)
                ret_dict.append(process)
            argcontent.child_list = ret_dict

        def _monitor(start_time, argcontent):
            while(int(time.mktime(datetime.datetime.now().timetuple())) - int(start_time) <
                    int(argcontent.timeout)):
                time.sleep(1)
                if argcontent.__subpro.poll() is not None:
                    self._subpro_data = argcontent.__subpro.communicate()
                    argcontent.ret['returncode'] = argcontent.__subpro.returncode
                    argcontent.ret['stdout'] = self._subpro_data[0]
                    argcontent.ret['stderr'] = self._subpro_data[1]
                    return
            str_warn = (
                'Shell "%s"execution timout:%d. To kill it' % (argcontent.cmd,
                    argcontent.timeout)
            )
            argcontent.__subpro.terminate()
            argcontent.ret['returncode'] = 999
            argcontent.ret['stderr'] = str_warn

            for process in argcontent.child_list:
                self.__kill_process(process)
            del argcontent.child_list[:]

        argcontent = Asynccontent()
        argcontent.cmd = cmd
        argcontent.timeout = timeout
        argcontent.ret = {
            'stdout': None,
            'stderr': None,
            'returncode': -999
        }
        argcontent.__cmdthd = threading.Thread(target=_target, args=(argcontent,))
        argcontent.__cmdthd.start()
        start_time = int(time.mktime(datetime.datetime.now().timetuple()))
        argcontent.__cmdthd.join(0.1)
        argcontent.pid = argcontent.__subpro.pid
        argcontent.__monitorthd = threading.Thread(target=_monitor,
                args=(start_time, argcontent))
        argcontent.__monitorthd.start()
        #this join should be del if i can make if quicker in Process.children
        argcontent.__cmdthd.join(0.5)
        return argcontent

    def run(self, cmd, timeout):
        """
        参见类说明。

        :param cmd:
            执行命令

        :param timeout:
            执行等待时间， None为无线等待。 timeout>=0等待具体时间，超时
            terminate.

        :return:
            一个dict, 包含'stdout' 'stderr' 'returncode' 三个key:

            returncode == 0 代表执行成功, returncode 999代表执行超时

            {
                'stdout' : 'Success',
                'stderr' : None,
                'returncode' : 0
            }

        E.g.

        执行ls， 超时时间为1s, 超过1s会kill掉该shell进程， 然后回返returncode
        999
        ::
            import cup
            shelltool = cup.shell.ShellExec()
            print shelltool.run('/bin/ls', timeout=1)
        """

        def _signal_handle():
            """
            signal setup
            """
            signal.signal(signal.SIGPIPE, signal.SIG_DFL)

        def _target(cmd):
            self._subpro = subprocess.Popen(
                cmd, shell=True, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=_signal_handle
            )
            self._subpro_data = self._subpro.communicate()
        ret = {
            'stdout': None,
            'stderr': None,
            'returncode': 0
        }
        cmdthd = threading.Thread(target=_target, args=(cmd, ))
        cmdthd.start()
        cmdthd.join(timeout)
        if cmdthd.isAlive() is True:
            str_warn = (
                'Shell "%s"execution timout:%d. To kill it' % (cmd, timeout)
            )
            warnings.warn(str_warn, RuntimeWarning)
            self._subpro.terminate()
            ret['returncode'] = 999
            ret['stderr'] = str_warn
        else:
            self._subpro.wait()
            times = 0
            while self._subpro.returncode is None and times < 10:
                time.sleep(1)
                times += 1
            ret['returncode'] = self._subpro.returncode
            assert type(self._subpro_data) == tuple, \
                'self._subpro_data should be a tuple'
            ret['stdout'] = self._subpro_data[0]
            ret['stderr'] = self._subpro_data[1]
        return ret


def _do_execshell(cmd, b_printcmd=True, timeout=None):
    """
    timeout默认赋值None，代表一直等待直到执行结束. 其他情况 >=0
    """
    if timeout is not None and timeout < 0:
        raise cup.err.ShellException(
            'timeout should be None or >= 0'
        )
    if b_printcmd is True:
        print 'To exec cmd:%s' % cmd
    shellexec = ShellExec()
    return shellexec.run(cmd, timeout)


def execshell(cmd, b_printcmd=True):
    """
    执行shell命令，返回returncode
    """
    return _do_execshell(cmd, b_printcmd=b_printcmd)['returncode']


def execshell_withpipe(cmd):
    """
    以popen的方式执行某条shell命令， 返回os.popen(cmd)
    Deprecated. 不推荐使用， 推荐使用ShellExec
    """
    res = os.popen(cmd)
    return res


def execshell_withpipe_ex(cmd, b_printcmd=True):
    """
    历史兼容函数。
    执行某条shell命令，回返执行stdout的结果行（list).
    Deprecated. 不推荐使用， 推荐使用ShellExec.
    """
    strfile = '/tmp/%s.%d.%d' % (
        'shell_env.py', int(os.getpid()), random.randint(100000, 999999)
    )
    os.mknod(strfile)
    cmd = cmd + ' 1>' + strfile + ' 2>/dev/null'
    os.system(cmd)
    if True == b_printcmd:
        print cmd
    fphandle = open(strfile, 'r')
    lines = fphandle.readlines()
    fphandle.close()
    os.unlink(strfile)
    return lines


def execshell_withpipe_str(cmd, b_printcmd=True):
    """
    历史兼容函数。
    同execshell_withpipe_ex, 但回返信息是string. (将所有行join成一个string回返)
    """
    return ''.join(execshell_withpipe_ex(cmd, b_printcmd))


def execshell_withpipe_exwitherr(cmd, b_printcmd=True):
    """
    历史兼容函数。 不推荐使用
    同execshell_withpipe_ex, 但回返信息是string. (将所有行join成一个string回返)
    该函数会将stdout和stderr一同回返。
    """
    strfile = '/tmp/%s.%d.%d' % (
        'shell_env.py', int(os.getpid()), random.randint(100000, 999999)
    )
    cmd = cmd + ' >' + strfile
    cmd = cmd + ' 2>&1'
    os.system(cmd)
    if b_printcmd:
        print cmd
    fhandle = open(strfile, 'r')
    lines = fhandle.readlines()
    fhandle.close()
    os.unlink(strfile)
    return lines


def is_proc_alive(procname, is_whole_word=False, is_server_tag=False, filters=False):
    """
    通过ps -ef|grep -w procname$ |grep -v grep|wc -l 判断进程是否存在
    相关函数有: cup.oper.is_proc_exist(path, name)
    """
    # print procName
    if is_whole_word:
        cmd = "ps -ef|grep -w '%s'$ |grep -v grep" % procname
    else:
        cmd = "ps -ef|grep -w '%s' |grep -v grep" % procname

    if is_server_tag:
        cmd += '|grep -vwE "vim |less |vi |tail |cat |more "'

    if filters:
        if type(filters) == str:
            cmd += "|grep -v '%s'" % filters
        elif type(filters) == list:
            for i, task in enumerate(filters):
                cmd += "|grep -v '%s'" % task

    cmd += '|wc -l'

    # print cmd
    rev = execshell_withpipe_str(cmd, False)
    if int(rev) > 0:
        return True
    else:
        return False


def forkexe_shell(cmd):
    """
    fock一个进程并在该进程执行shell的cmd命令
    """
    try:
        pid = os.fork()
        if pid > 0:
            return
    except OSError:
        sys.exit(1)
    # os.chdir("/")
    os.setsid()
    # os.umask(0)
    try:
        pid = os.fork()
        if pid > 0:
            sys.exit(0)
    except OSError:
        sys.exit(1)
    os.system(cmd)


def md5file(filename):
    """
        计算一个文件的md5值。返回32位长的hex字符串。
    """
    if os.path.exists(filename) is False:
        raise IOError('No such file: %s' % filename)
    with open(filename, 'rb') as fhandle:
        md5obj = hashlib.md5()
        while True:
            strtmp = fhandle.read(131072)  # read 128k one time
            if len(strtmp) <= 0:
                break
            md5obj.update(strtmp)
    return md5obj.hexdigest()


def kill9_byname(strname):
    """
    kill -9 process by name
    """
    fd_pid = os.popen("ps -ef | grep -v grep |grep %s \
            |awk '{print $2}'" % (strname))
    pids = fd_pid.read().strip().split('\n')
    fd_pid.close()
    for pid in pids:
        os.system("kill -9 %s" % (pid))


def kill_byname(strname):
    """
    kill process by name
    """
    fd_pid = os.popen("ps -ef | grep -v grep |grep %s \
            |awk '{print $2}'" % (strname))
    pids = fd_pid.read().strip().split('\n')
    fd_pid.close()
    for pid in pids:
        os.system("kill -s SIGKILL %s" % (pid))


def del_if_exist(path):
    """
    如果文件/目录/symlink存在则删除他们
    """
    if path == '/':
        raise IOError('Cannot delete root path /')
    if os.path.lexists(path) is False:
        return -1
    if os.path.isdir(path):
        shutil.rmtree(path)
    elif os.path.isfile(path) or os.path.islink(path):
        os.unlink(path)
    else:
        raise IOError('Does not support deleting the type 4 the path')


def rmtree(path, ignore_errors=False, onerror=None, safemode=True):
    """
    safe rmtree.

    safemode, by default is True, which forbids:

    1. not allowing rmtree root "/"

    """
    if safemode:
        if os.path.normpath(os.path.abspath(path)) == '/':
            raise err.ShellException('cannot rmtree root / under safemode')
    if os.path.isfile(path):
        return os.unlink(path)
    else:
        return shutil.rmtree(path, ignore_errors, onerror)


def shell_diff(srcfile, dstfile):
    """
    调用shell环境的diff命令diff两个文件， 回返diff信息。
    无diff回返0， 有diff回返非0
    """
    cmd = 'diff %s %s' % (srcfile, dstfile)
    return os.system(cmd)


def get_pid(process_path, grep_string):
    """
    will return immediately after find the pid which matches

    1. ps -ef|grep %s|grep -v grep|grep -vE "^[vim|less|vi|tail|cat|more] "
    '|awk '{print $2}'

    2. workdir is the same as ${process_path}

    :param process_path:
        process that runs on
    :param grep_string:
        ps -ef|grep ${grep_string}
    :return:
        return None if not found. Otherwise, return the pid

    """
    cmd = (
        'ps -ef|grep \'%s\'|grep -v grep|grep -vwE "vim |less |vi |tail |cat |more "'
        '|awk \'{print $2}\''
    ) % (grep_string)
    ret = cup.shell.ShellExec().run(cmd, 10)
    pids = ret['stdout'].strip().split('\n')
    if len(pids) == 0 or len(pids) == 1 and len(pids[0]) == 0:
        return None
    for pid in pids:
        for sel_path in ["cwd", "exe"]:
            cmd = 'ls -l /proc/%s/%s|awk \'{print $11}\' ' % (pid, sel_path)
            ret = cup.shell.ShellExec().run(cmd, 10)
            pid_path = ret['stdout'].strip().strip()
            if pid_path.find(process_path) == 0:
                return pid
    return None


def _test():
    pass


if __name__ == '__main__':
    _test()

# vi:set tw=0 ts=4 sw=4 nowrap fdm=indent
