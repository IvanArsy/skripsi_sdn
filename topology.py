from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.cli import CLI
from mininet.log import setLogLevel

def myNetwork():
    net = Mininet(topo=None, build=False, ipBase='10.0.0.0/8')

    print('--Adding Controller--')
    net.addController(name='c0', controller=RemoteController, ip='127.0.0.1', port=6633)

    print('--Adding Host and Switches--')
    h1 = net.addHost('h1', ip='10.0.0.1')
    h2 = net.addHost('h2', ip='10.0.0.2')
    s1 = net.addSwitch('s1', cls=OVSSwitch, protocols='OpenFlow13')

    print('--Creating Links--')
    net.addLink(h1, s1)
    net.addLink(h2, s1)

    print('--Starting Network--')
    net.start()
    CLI(net)
    net.stop()

if __name__ == '__main__':
    setLogLevel('info')
    myNetwork()