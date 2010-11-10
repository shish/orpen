#!/usr/bin/env python

from optparse import OptionParser
from threading import Thread
import sys
import socket
import struct
import time
from select import select
import logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("orpen")

class Connection(object):
    def read(self, size):
        pass

    def write(self, data):
        pass

    def fileno(self):
        pass

    def close(self):
        pass

class TCPConnection(Connection):
    def __init__(self, url):
        if ":" in url:
            (host, port) = url.split(":")
        else:
            (host, port) = (url, 24142)
        self._conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._conn.connect((host, port))

    def read(self, size):
        return self._conn.recv(size)

    def write(self, data):
        return self._conn.sendall(data)

    def fileno(self):
        return self._conn

    def close(self):
        self._conn.close()


def connect(server):
    log.info("Connecting to "+server)
    (proto, host) = server.split("://")
    if proto == "tcp":
        conn = TCPConnection(host)
    addr = "%d.%d.%d.%d/%d" % tuple([ord(c) for c in struct.unpack("ccccc", conn.read(5))])

    log.info("Opening TAP device with address="+addr)
    dev = TapDevice(mode=IFF_TAP, name='py')
    dev.ifconfig(address=addr)
    dev.up()

    return conn, dev

def disconnect(conn, dev):
    try:
        conn.close()
    except Exception, e:
        pass
    try:
        dev.close()
    except Exception, e:
        pass

def wibble(conn, dev):
    log.info("Wibbling traffic")
    while True:
        readable, writable, errable = select([conn, dev], [], [conn, dev])
        if conn in readable:
            data = conn.read(1024*4)
            if len(data) == 0:
                return
            #log.debug("Read "+str(len(data))+" bytes from the network")
            dev.write(data)
        if dev in readable:
            data = dev.read()
            #log.debug("Writing "+str(len(data))+" bytes to the network")
            conn.write(data)
        if len(errable) > 0:
            raise Exception("A stream had an error")

def main(args):
    conn, dev = None, None
    while True:
        try:
            conn, dev = connect(args[1])
            wibble(conn, dev)
        except KeyboardInterrupt:
            log.info("Interrupted, exiting")
            return 0
        except Exception, e:
            log.exception("Error detected, sleeping 5 seconds then reconnecting")
            time.sleep(5)
        finally:
            disconnect(conn, dev)



'''
TapDevice and IfconfigError classes copied from pytap, and
a fileno() method added to TapDevice so that the device can
be passed to select()

------------

PyTap module that wraps the Linux TUN/TAP device

@author: Dominik George
'''

from fcntl import ioctl
import os
import struct
import atexit

TUNSETIFF = 0x400454ca
IFF_TUN   = 0x0001
IFF_TAP   = 0x0002

DEFAULT_MTU = 1500

class TapDevice:
    ''' TUN/TAP device object '''

    def __init__(self, mode = IFF_TUN, name = '', dev = '/dev/net/tun'):
        '''
        Initialize TUN/TAP device object

        mode is either IFF_TUN or IFF_TAP to select tun or tap device mode.

        name is the name of the new device. An integer will be added to
        build the real device name.

        dev is the device node name the control channel is connected to.
        '''

        # Set interface mdoe in object
        self.mode = mode

        # Create interface name to request from tuntap module
        if name == '':
            if self.mode == IFF_TUN:
                self.name = 'tun%d'
            elif self.mode == IFF_TAP:
                self.name = 'tap%d'
        elif name.endswith('%d'):
            self.name = name
        else:
            self.name = name + '%d'
        
        # Open control device and request interface
        fd = os.open(dev, os.O_RDWR)
        ifs = ioctl(fd, TUNSETIFF, struct.pack("16sH", self.name, self.mode))
        
        # Retreive real interface name from control device
        self.name = ifs[:16].strip("\x00")
        
        # Set default MTU
        self.mtu = DEFAULT_MTU
        
        # Store fd for later
        self.__fd__ = fd
        
        # Properly close device on exit
        atexit.register(self.close)
        
    def read(self):
        '''
        Read data from the device. The device mtu determines how many bytes
        will be read.

        The data read from the device is returned in its raw form.
        '''

        data = os.read(self.__fd__, self.mtu)
        return data
    
    def write(self, data):
        '''
        Write data to the device. No care is taken for MTU limitations or similar.
        '''

        os.write(self.__fd__, data)

    def fileno(self):
        return self.__fd__
        
    def ifconfig(self, **args):
        '''
        Issue ifconfig command on the device. The method takes the following
        keyword arguments:

         address   => IP address of the device, can be in CIDR notation (see man ifconfig)
         netmask   => Network mask
         network   => Network base address, normally set automatically
         broadcast => Broadcast address, normally set automatically
         mtu       => Link MTU, this will also affect the read() method
         hwclass   => Hardware class, normally ether for ethernet
         hwaddress => Hardware (MAC) address, in conjunction with hwclass
        '''
        
        ifconfig = 'ifconfig ' + self.name + ' '
        
        # IP address ?
        try:
            ifconfig = ifconfig + args['address'] + ' '
        except KeyError:
            pass
        
        # Network mask ?
        try:
            ifconfig = ifconfig + 'netmask ' + args['netmask'] + ' '
        except KeyError:
            pass
        
        # Network base address ?
        try:
            ifconfig = ifconfig + 'network ' + args['network'] + ' '
        except KeyError:
            pass
        
        # Broadcast address ?
        try:
            ifconfig = ifconfig + 'broadcast ' + args['broadcast'] + ' '
        except KeyError:
            pass
        
        # MTU ?
        try:
            ifconfig = ifconfig + 'mtu ' + str(args['mtu']) + ' '
        except KeyError:
            pass
        
        # Hardware address ?
        try:
            ifconfig = ifconfig + 'hw ' + args['hwclass'] + ' ' + args['hwaddress'] + ' '
        except KeyError:
            pass
        
        # Try to set off ifconfig command
        ret = os.system(ifconfig)
        
        if ret != 0:
            raise IfconfigError()
        
        # Save MTU if ifconfig was successful so buffer sizes can be adjusted
        try:
            self.mtu = args['mtu']
        except KeyError:
            pass

    def up(self):
        '''
        Bring up device. This will effectively run "ifconfig up" on the device.
        '''

        ret = os.system("ifconfig " + self.name + " up")
        
        if ret != 0:
            raise IfconfigError()
        
    def down(self):
        '''
        Bring down device. This will effectively call "ifconfig down" on the device.
        '''

        ret = os.system("ifconfig " + self.name + " down")
        
        if ret != 0:
            raise IfconfigError()
        
    def close(self):
        '''
        Close the control channel. This will effectively drop all locks and remove the
        TUN/TAP device.

        You must manually take care that your code does not try to operate on the interface
        after closing the control channel.
        '''

        if self.__fd__:
            os.close(self.__fd__)
            self.__fd__ = None

        
class IfconfigError(Exception):
    ''' Exception thrown if an ifconfig command returns with a non-zero exit status. '''

    pass
        
if __name__ == "__main__":
    sys.exit(main(sys.argv))
