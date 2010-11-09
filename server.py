#!/usr/bin/twistd -noy

from twisted.internet.protocol import Protocol, Factory
import struct
import logging

logging.basicConfig(level=logging.INFO)

class Client(Protocol):
    def connectionMade(self):
        logging.info("Connection added")
        for n in range(2, 250):
            if n not in self.factory.ips:
                self.ip = n
                break
        self.transport.write(struct.pack("ccccc", chr(10), chr(162), chr(220), chr(self.ip), chr(24)))
        self.factory.clients.append(self)
        self.factory.ips.append(self.ip)

    def connectionLost(self, reason):
        logging.info("Connection lost")
        self.factory.clients.remove(self)
        self.factory.ips.remove(self.ip)

    def dataReceived(self, data):
        logging.debug("Spreading "+str(len(data))+" bytes to "+str(len(self.factory.clients))+" clients")
        for p in self.factory.clients:
            if p != self:
                p.transport.write(data)


clients = []
ips = []

f_tcp = Factory()
f_tcp.protocol = Client
f_tcp.clients = clients
f_tcp.ips = ips


from twisted.python import log
observer = log.PythonLoggingObserver()
observer.start()

from twisted.application import internet, service
from twisted.internet import reactor
application = service.Application("orpend")  # create the Application
tcpService = internet.TCPServer(24142, f_tcp) # create the service
tcpService.setServiceParent(application)

