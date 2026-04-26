from mininet.topo import Topo

class PartialMeshTopo( Topo ):
    "Topologi 5x6 Partial Mesh dengan 5 Host per Switch"

    def build( self ):
        rows = 5
        cols = 6
        hosts_per_switch = 5
        
        switches = {}
        host_counter = 1
        switch_counter = 1

        for r in range(rows):
            for c in range(cols):
                s_name = f's{switch_counter}'
                s = self.addSwitch(s_name)
                switches[(r, c)] = s
                switch_counter += 1
                
                for h in range(hosts_per_switch):
                    h_name = f'h{host_counter}'
                    host = self.addHost(h_name)
                    self.addLink(host, s)
                    host_counter += 1


        for r in range(rows):
            for c in range(cols):
                current_switch = switches[(r, c)]
                
                if c + 1 < cols:
                    east_switch = switches[(r, c + 1)]
                    self.addLink(current_switch, east_switch)
                    
                if r + 1 < rows:
                    south_switch = switches[(r + 1, c)]
                    self.addLink(current_switch, south_switch)
                    
                if r + 1 < rows and c + 1 < cols:
                    se_switch = switches[(r + 1, c + 1)]
                    self.addLink(current_switch, se_switch)

topos = { 'mytopo': ( lambda: PartialMeshTopo() ) }