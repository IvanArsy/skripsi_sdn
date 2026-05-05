from mininet.topo import Topo

class PartialMeshTopo( Topo ):
    "Topologi 5x6 Edge-Core - 50 Pengirim (Kiri) & 50 Penerima (Kanan)"

    def build( self ):
        rows = 5
        cols = 6
        switches = {}
        switch_counter = 1
        host_counter = 1

        for r in range(rows):
            for c in range(cols):
                s_name = f's{switch_counter}'
                s = self.addSwitch(s_name)
                switches[(r, c)] = s
                
                # 10 Host di 5 Switch Kiri
                if c == 0:
                    for _ in range(10):
                        h = self.addHost(f'h{host_counter}')
                        self.addLink(h, s, bw=100)
                        host_counter += 1
                    
                # 10 Host di 5 Switch Kanan
                elif c == cols - 1:
                    for _ in range(10):
                        h = self.addHost(f'h{host_counter}')
                        self.addLink(h, s, bw=100)
                        host_counter += 1
                    
                switch_counter += 1

        # Link Core Network
        for r in range(rows):
            for c in range(cols):
                curr = switches[(r, c)]
                if c + 1 < cols:
                    self.addLink(curr, switches[(r, c + 1)], bw=10, max_queue_size=100)
                if r + 1 < rows:
                    self.addLink(curr, switches[(r + 1, c)], bw=10, max_queue_size=100)
                if r + 1 < rows and c + 1 < cols:
                    self.addLink(curr, switches[(r + 1, c + 1)], bw=10, max_queue_size=100)

topos = { 'mytopo': ( lambda: PartialMeshTopo() ) }