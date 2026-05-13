from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import (
    CONFIG_DISPATCHER,
    MAIN_DISPATCHER,
    DEAD_DISPATCHER,
    set_ev_cls
)
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ether_types, arp, ipv4
from ryu.topology import event
from ryu.lib import hub

import networkx as nx
import numpy as np
import time
from itertools import islice

class TopsisSDNController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    MONITOR_INTERVAL = 3 
    MAX_PATHS = 3
    LINK_CAPACITY = 10.0

    def __init__(self, *args, **kwargs):
        super(TopsisSDNController, self).__init__(*args, **kwargs)
        self.net = nx.DiGraph()
        self.datapaths = {}
        self.hosts = {}
        self.internal_ports = {}
        self.link_metrics = {}
        self.port_stats = {}
        self.path_cache = {}

        self.monitor_thread = hub.spawn(self._monitor)

    # SWITCH STATE & TABLE MISS
    @set_ev_cls(ofp_event.EventOFPStateChange, [MAIN_DISPATCHER, DEAD_DISPATCHER])
    def state_change_handler(self, ev):
        datapath = ev.datapath
        if ev.state == MAIN_DISPATCHER:
            if datapath.id not in self.datapaths:
                self.datapaths[datapath.id] = datapath
                self.logger.info("REGISTER SWITCH s%s", datapath.id)
        elif ev.state == DEAD_DISPATCHER:
            if datapath.id in self.datapaths:
                del self.datapaths[datapath.id]

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions)

    # TOPOLOGY DISCOVERY
    @set_ev_cls(event.EventLinkAdd)
    def link_add_handler(self, ev):
        s1, s2 = ev.link.src.dpid, ev.link.dst.dpid
        p1 = ev.link.src.port_no

        if not self.net.has_edge(s1, s2):
            self.net.add_edge(s1, s2, port=p1)
            self.internal_ports.setdefault(s1, set()).add(p1)
            self.link_metrics[(s1, s2)] = {"bw": 10.0, "loss": 0.0, "delay": 1.0}

    # MONITOR THREAD
    def _monitor(self):
        self.logger.info("SENSOR JARINGAN AKTIF...")
        while True:
            for dp in self.datapaths.values():
                self._request_stats(dp)
            hub.sleep(self.MONITOR_INTERVAL)

    def _request_stats(self, datapath):
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto
        req = parser.OFPPortStatsRequest(datapath, 0, ofproto.OFPP_ANY)
        datapath.send_msg(req)

    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def port_stats_reply_handler(self, ev):
        dpid = ev.msg.datapath.id
        current_time = time.time()

        for stat in ev.msg.body:
            port_no = stat.port_no
            if port_no == ev.msg.datapath.ofproto.OFPP_LOCAL:
                continue

            self.port_stats.setdefault(dpid, {})
            if port_no in self.port_stats[dpid]:
                old_bytes, old_drop, old_time = self.port_stats[dpid][port_no]
                delta_bytes = stat.tx_bytes - old_bytes
                delta_time = current_time - old_time

                throughput = (delta_bytes * 8.0 / 1000000.0) / max(delta_time, 0.0001)
                remaining_bw = max(self.LINK_CAPACITY - throughput, 0.1)

                delta_drop = stat.tx_dropped - old_drop
                loss = (delta_drop / stat.tx_packets) * 100.0 if stat.tx_packets > 0 else 0.0

                for u, v, data in self.net.edges(data=True):
                    if u == dpid and data['port'] == port_no:
                        self.link_metrics[(u, v)] = {
                            "bw": remaining_bw,
                            "loss": loss,
                            "delay": 1.0 
                        }

            self.port_stats[dpid][port_no] = (stat.tx_bytes, stat.tx_dropped, current_time)

    # PACKET IN (LOGIKA UTAMA)
    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto
        dpid = datapath.id
        in_port = msg.match['in_port']

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)
        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        dst = eth.dst
        src = eth.src
        ip_pkt = pkt.get_protocol(ipv4.ipv4)

        if in_port not in self.internal_ports.get(dpid, set()):
            self.hosts[src] = (dpid, in_port)

        if dst in self.hosts:
            dst_switch, dst_port = self.hosts[dst]

            try:
                if dpid == dst_switch:
                    out_port = dst_port
                else:
                    paths = self._get_k_paths(dpid, dst_switch)
                    if not paths:
                        return

                    matrix = []
                    for path in paths:
                        bw = 9999.0
                        delay = 0.0
                        loss = 0.0
                        for i in range(len(path) - 1):
                            u, v = path[i], path[i + 1]
                            metric = self.link_metrics.get((u, v), {"bw": 10.0, "delay": 1.0, "loss": 0.0})
                            bw = min(bw, metric["bw"])
                            delay += metric["delay"]
                            loss += metric["loss"]
                        matrix.append([bw, delay, loss])

                    best_idx = self._topsis(matrix)
                    best_path = paths[best_idx]
                    next_hop = best_path[1]
                    out_port = self.net[dpid][next_hop]['port']

                    if ip_pkt and matrix[best_idx][0] < 9.0:
                        self.logger.info(f"[TOPSIS] s{dpid}->s{dst_switch} | IP: {ip_pkt.src}->{ip_pkt.dst} | Rute: {best_path} | BW: {matrix[best_idx][0]:.2f}M")

                actions = [parser.OFPActionOutput(out_port)]

                if ip_pkt:
                    match = parser.OFPMatch(
                        in_port=in_port,
                        eth_type=0x0800,
                        ipv4_src=ip_pkt.src,
                        ipv4_dst=ip_pkt.dst
                    )
                    self.add_flow(datapath, 10, match, actions, idle_timeout=10, hard_timeout=30)

                out = parser.OFPPacketOut(
                    datapath=datapath, buffer_id=msg.buffer_id,
                    in_port=in_port, actions=actions, data=msg.data
                )
                datapath.send_msg(out)
                return

            except Exception as e:
                self.logger.error("PATH ERROR %s", str(e))
                return

        arp_pkt = pkt.get_protocol(arp.arp)
        if arp_pkt:
            for sw, dp in self.datapaths.items():
                parser2 = dp.ofproto_parser
                ofproto2 = dp.ofproto
                for port in dp.ports.keys():
                    if port == ofproto2.OFPP_LOCAL: continue
                    if port in self.internal_ports.get(sw, set()): continue
                    if sw == dpid and port == in_port: continue

                    actions = [parser2.OFPActionOutput(port)]
                    out = parser2.OFPPacketOut(
                        datapath=dp, buffer_id=ofproto2.OFP_NO_BUFFER,
                        in_port=ofproto2.OFPP_CONTROLLER, actions=actions, data=msg.data
                    )
                    dp.send_msg(out)

    # K-PATH CACHE (Penyelamat CPU)
    def _get_k_paths(self, src, dst):
        key = (src, dst)
        if key in self.path_cache:
            return self.path_cache[key]
        try:
            paths = list(islice(nx.shortest_simple_paths(self.net, src, dst), self.MAX_PATHS))
            self.path_cache[key] = paths
            return paths
        except:
            return []

    # TOPSIS ALGORITHM
    def _topsis(self, matrix):
        if len(matrix) <= 1:
            return 0

        X = np.array(matrix, dtype=float)
        X[X == 0] = 0.0001
        weights = np.array([0.4, 0.3, 0.3])
        divisor = np.sqrt(np.sum(X ** 2, axis=0))
        
        divisor[divisor == 0] = 1e-10 
        
        R = X / divisor
        V = R * weights

        ideal_pos = np.array([np.max(V[:, 0]), np.min(V[:, 1]), np.min(V[:, 2])])
        ideal_neg = np.array([np.min(V[:, 0]), np.max(V[:, 1]), np.max(V[:, 2])])

        D_pos = np.sqrt(np.sum((V - ideal_pos) ** 2, axis=1))
        D_neg = np.sqrt(np.sum((V - ideal_neg) ** 2, axis=1))

        score = D_neg / (D_pos + D_neg + 1e-10)
        return np.argmax(score)

    # FLOW INSTALLER DENGAN TIMEOUT
    def add_flow(self, datapath, priority, match, actions, idle_timeout=0, hard_timeout=0):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        mod = parser.OFPFlowMod(
            datapath=datapath, priority=priority, match=match,
            instructions=inst, idle_timeout=idle_timeout, hard_timeout=hard_timeout
        )
        datapath.send_msg(mod)