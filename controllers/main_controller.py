from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import (
    CONFIG_DISPATCHER,
    MAIN_DISPATCHER,
    DEAD_DISPATCHER,
    set_ev_cls,
)
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import (
    packet,
    ethernet,
    ether_types,
    arp,
    ipv4,
)
from ryu.topology import event
from ryu.lib import hub

import networkx as nx
import numpy as np
import time
import csv
import os

from itertools import islice


class BaseRoutingController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    MONITOR_INTERVAL = 3
    MAX_PATHS = 3
    LINK_CAPACITY = 15.0
    DEFAULT_DELAY_MS = 5.0
    PATH_CACHE_TTL = 5
    TOPO_LINK_CAPACITY = {
    "horizontal": 15,
    "vertical":   10,
    "diagonal":    5,
    }
    ROUTING_MODE = "BASE"

    def __init__(self, *args, **kwargs):
        super(BaseRoutingController, self).__init__(*args, **kwargs)

        self.net = nx.DiGraph()
        self.datapaths = {}
        self.hosts = {}
        self.internal_ports = {}
        self.link_metrics = {}
        self.port_stats = {}
        self.path_cache = {}
        self.cache_counter = 0
        self.last_path = {}
        self.echo_latency = {}
        self.echo_send_time = {}
        self.link_capacity = {}   

        self.csv_file = f"{self.ROUTING_MODE}_controller_log.csv"

        if not os.path.exists(self.csv_file):
            with open(self.csv_file, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "timestamp",
                    "src_ip",
                    "dst_ip",
                    "selected_path",
                    "throughput_mbps",
                    "delay_ms",
                    "loss_pct",
                    "exec_time_ms",
                    "path_changed",
                    "topsis_scores",
                ])

        self.monitor_thread = hub.spawn(self._monitor)


    @set_ev_cls(
        ofp_event.EventOFPStateChange,
        [MAIN_DISPATCHER, DEAD_DISPATCHER],
    )
    def state_change_handler(self, ev):
        datapath = ev.datapath
        if ev.state == MAIN_DISPATCHER:
            if datapath.id not in self.datapaths:
                self.datapaths[datapath.id] = datapath
                self.logger.info("REGISTER SWITCH s%s", datapath.id)

        elif ev.state == DEAD_DISPATCHER:
            if datapath.id in self.datapaths:
                del self.datapaths[datapath.id]
                self.echo_latency.pop(datapath.id, None)
                self.echo_send_time.pop(datapath.id, None)


    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        match = parser.OFPMatch()
        actions = [
            parser.OFPActionOutput(
                ofproto.OFPP_CONTROLLER,
                ofproto.OFPCML_NO_BUFFER,
            )
        ]
        self.add_flow(datapath, 0, match, actions)

    def _get_link_capacity(self, s1: int, s2: int) -> float:
            """
            Tentukan kapasitas link berdasarkan posisi switch di grid 5×6.
            Switch dinomori 1-30, berurutan row-by-row kiri ke kanan.

            Grid:
                s1  s2  s3  s4  s5  s6
                s7  s8  ...
                ...
                s25 s26 s27 s28 s29 s30

            Horizontal : s(r,c) → s(r,c+1)  selisih dpid = 1
            Vertikal   : s(r,c) → s(r+1,c)  selisih dpid = 6 (cols)
            Diagonal   : s(r,c) → s(r+1,c+1) selisih dpid = 7
            """
            cols = 6
            diff = abs(s2 - s1)
            if diff == 1:
                return self.TOPO_LINK_CAPACITY["horizontal"]
            elif diff == cols:
                return self.TOPO_LINK_CAPACITY["vertical"]
            elif diff == cols + 1:
                return self.TOPO_LINK_CAPACITY["diagonal"]
            else:
                return min(self.TOPO_LINK_CAPACITY.values())  

    @set_ev_cls(event.EventLinkAdd)
    def link_add_handler(self, ev):
        s1 = ev.link.src.dpid
        s2 = ev.link.dst.dpid
        p1 = ev.link.src.port_no

        capacity = self._get_link_capacity(s1, s2)

        if not self.net.has_edge(s1, s2):
            self.net.add_edge(
                s1, s2,
                port=p1,
                delay=self.DEFAULT_DELAY_MS,
                loss=0.0,
                bw=capacity,
            )

            self.internal_ports.setdefault(s1, set()).add(p1)

            self.link_metrics[(s1, s2)] = {
                "bw": capacity,
                "delay": self.DEFAULT_DELAY_MS,
                "loss": 0.0,
            }

            self.link_capacity[(s1, s2)] = capacity


    def _monitor(self):
        self.logger.info("%s MONITOR STARTED", self.ROUTING_MODE)

        while True:
            for dp in list(self.datapaths.values()):
                self._request_port_stats(dp)
                self._send_echo_request(dp)

            self.cache_counter += 1
            if self.cache_counter >= self.PATH_CACHE_TTL:
                self.path_cache.clear()
                self.cache_counter = 0

            hub.sleep(self.MONITOR_INTERVAL)


    def _request_port_stats(self, datapath):
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto
        req = parser.OFPPortStatsRequest(datapath, 0, ofproto.OFPP_ANY)
        datapath.send_msg(req)


    def _send_echo_request(self, datapath):
        parser = datapath.ofproto_parser
        self.echo_send_time[datapath.id] = time.time()
        echo = parser.OFPEchoRequest(datapath, data=b"")
        datapath.send_msg(echo)

    @set_ev_cls(ofp_event.EventOFPEchoReply, MAIN_DISPATCHER)
    def echo_reply_handler(self, ev):
        dpid = ev.msg.datapath.id
        if dpid in self.echo_send_time:
            rtt_ms = (time.time() - self.echo_send_time[dpid]) * 1000.0
            prev = self.echo_latency.get(dpid, rtt_ms)
            self.echo_latency[dpid] = 0.5 * prev + 0.5 * rtt_ms

            self.logger.debug(
                "ECHO s%s RTT=%.2f ms", dpid, self.echo_latency[dpid]
            )


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
                (
                    old_bytes,
                    old_drop,
                    old_packets,
                    old_time,
                ) = self.port_stats[dpid][port_no]

                delta_bytes = stat.tx_bytes - old_bytes
                delta_drop = stat.tx_dropped - old_drop
                delta_packets = stat.tx_packets - old_packets
                delta_time = current_time - old_time
                
                

                if delta_bytes < 0 or delta_drop < 0 or delta_packets < 0:
                    self.port_stats[dpid][port_no] = (
                        stat.tx_bytes,
                        stat.tx_dropped,
                        stat.tx_packets,
                        current_time,
                    )
                    continue

                delta_time = max(delta_time, 0.0001)

                throughput_mbps = (delta_bytes * 8.0 / 1_000_000.0) / delta_time

                if delta_packets > 0:
                    loss_pct = (delta_drop / delta_packets) * 100.0
                else:
                    loss_pct = 0.0

                if throughput_mbps >= 1.0:
                    self.logger.warning(
                        "[PORT_STATS] s%s port=%s "
                        "tx_pkt=%s rx_pkt=%s "
                        "tx_drop=%s rx_drop=%s "
                        "tx_err=%s rx_err=%s "
                        "coll=%s",
                        dpid,
                        port_no,
                        stat.tx_packets,
                        stat.rx_packets,
                        stat.tx_dropped,
                        stat.rx_dropped,
                        stat.tx_errors,
                        stat.rx_errors,
                        stat.collisions
                    )

                rtt_u = self.echo_latency.get(dpid, self.DEFAULT_DELAY_MS)

                for u, v, data in self.net.edges(data=True):
                    if u == dpid and data.get("port") == port_no:

                        cap          = self.link_capacity.get((u, v), self.LINK_CAPACITY)
                        remaining_bw = max(cap - throughput_mbps, 0.1)

                        rtt_v         = self.echo_latency.get(v, self.DEFAULT_DELAY_MS)
                        link_delay_ms = max((rtt_u + rtt_v) / 2.0, 0.1)

                        self.link_metrics[(u, v)] = {
                            "bw":    remaining_bw,
                            "delay": link_delay_ms,
                            "loss":  loss_pct,
                        }
                        self.net[u][v]["delay"] = link_delay_ms
                        self.net[u][v]["loss"]  = loss_pct
                        self.net[u][v]["bw"]    = remaining_bw

                        self.logger.debug(
                            "LINK s%s→s%s  bw=%.2f Mbps  delay=%.2f ms  loss=%.4f%%",
                            u, v, remaining_bw, link_delay_ms, loss_pct,
                        )
                        break

            self.port_stats[dpid][port_no] = (
                stat.tx_bytes,
                stat.tx_dropped,
                stat.tx_packets,
                current_time,
            )


    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto
        dpid = datapath.id
        in_port = msg.match["in_port"]
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
                    exec_time_ms = 0.0
                    best_path = [dpid]
                    topsis_scores_str = ""
                    path_changed = 0
                else:
                    start_time = time.time()

                    best_path, topsis_scores = self.select_path(
                        dpid, dst_switch
                    )

                    exec_time_ms = (time.time() - start_time) * 1000.0

                    next_hop = best_path[1]
                    out_port = self.net[dpid][next_hop]["port"]

                    path_changed = 0
                    if ip_pkt:
                        flow_key = (ip_pkt.src, ip_pkt.dst)
                        if (
                            flow_key in self.last_path
                            and self.last_path[flow_key] != best_path
                        ):
                            path_changed = 1
                        self.last_path[flow_key] = best_path

                    topsis_scores_str = (
                        "|".join(f"{s:.4f}" for s in topsis_scores)
                        if topsis_scores
                        else ""
                    )

                if ip_pkt and len(best_path) > 1:
                    path_metric = self.calculate_path_metric(best_path)
                    with open(self.csv_file, "a", newline="") as f:
                        writer = csv.writer(f)
                        writer.writerow([
                            time.time(),
                            ip_pkt.src,
                            ip_pkt.dst,
                            str(best_path),
                            round(path_metric["bw"], 4),
                            round(path_metric["delay"], 4),
                            round(path_metric["loss"], 4),
                            round(exec_time_ms, 4),
                            path_changed,
                            topsis_scores_str,     
                        ])

                self.logger.info(
                    "[%s] PATH=%s changed=%d exec=%.2fms",
                    self.ROUTING_MODE, best_path, path_changed, exec_time_ms,
                )

                actions = [parser.OFPActionOutput(out_port)]

                if ip_pkt:
                    match = parser.OFPMatch(
                        in_port=in_port,
                        eth_type=0x0800,
                        ipv4_src=ip_pkt.src,
                        ipv4_dst=ip_pkt.dst,
                    )
                    self.add_flow(
                        datapath, 10, match, actions, idle_timeout=10
                    )

                out = parser.OFPPacketOut(
                    datapath=datapath,
                    buffer_id=msg.buffer_id,
                    in_port=in_port,
                    actions=actions,
                    data=msg.data,
                )
                datapath.send_msg(out)
                return

            except Exception as e:
                self.logger.error("PACKET-IN ERROR: %s", str(e))
                return

        arp_pkt = pkt.get_protocol(arp.arp)
        if arp_pkt:
            for sw, dp in list(self.datapaths.items()):
                parser2 = dp.ofproto_parser
                ofproto2 = dp.ofproto

                for port in dp.ports.keys():
                    if port == ofproto2.OFPP_LOCAL:
                        continue
                    if port in self.internal_ports.get(sw, set()):
                        continue
                    if sw == dpid and port == in_port:
                        continue

                    actions = [parser2.OFPActionOutput(port)]
                    out = parser2.OFPPacketOut(
                        datapath=dp,
                        buffer_id=ofproto2.OFP_NO_BUFFER,
                        in_port=ofproto2.OFPP_CONTROLLER,
                        actions=actions,
                        data=msg.data,
                    )
                    dp.send_msg(out)


    def _get_k_paths(self, src, dst):
        key = (src, dst)
        if key in self.path_cache:
            return self.path_cache[key]

        try:
            paths = list(
                islice(
                    nx.shortest_simple_paths(
                        self.net,
                        src,
                        dst,
                        weight="delay",     
                    ),
                    self.MAX_PATHS,
                )
            )
            self.path_cache[key] = paths
            return paths

        except nx.NetworkXNoPath:
            self.logger.warning("No path from s%s to s%s", src, dst)
            return []
        except Exception as e:
            self.logger.error("_get_k_paths error: %s", str(e))
            return []


    def calculate_path_metric(self, path):
        bw = float("inf")
        delay = 0.0
        no_loss_prob = 1.0      
        for i in range(len(path) - 1):
            u, v = path[i], path[i + 1]
            metric = self.link_metrics.get(
                (u, v),
                {
                    "bw": self.link_capacity.get((u, v), self.LINK_CAPACITY),
                    "delay": self.DEFAULT_DELAY_MS,
                    "loss": 0.0,
                },
            )

            bw = min(bw, metric["bw"])
            delay += metric["delay"]

            link_loss_frac = metric["loss"] / 100.0
            link_loss_frac = min(max(link_loss_frac, 0.0), 1.0)
            no_loss_prob *= (1.0 - link_loss_frac)

        path_loss_pct = (1.0 - no_loss_prob) * 100.0

        if bw == float("inf"):
            bw = self.LINK_CAPACITY

        return {
            "bw": bw,
            "delay": delay,
            "loss": path_loss_pct,
        }


    def select_path(self, src, dst):
        raise NotImplementedError


    def _topsis(self, matrix):
        n = len(matrix)
        if n == 0:
            return 0, []
        if n == 1:
            return 0, [1.0]

        X = np.array(matrix, dtype=float)

        X = np.where(X == 0.0, 1e-6, X)

        denom = np.sqrt(np.sum(X ** 2, axis=0))
        denom = np.where(denom == 0.0, 1e-10, denom)
        R = X / denom

        weights = np.array([0.4, 0.3, 0.3])
        V = R * weights

        ideal_pos = np.array([
            np.max(V[:, 0]),   
            np.min(V[:, 1]),  
            np.min(V[:, 2]),   
        ])
        ideal_neg = np.array([
            np.min(V[:, 0]),
            np.max(V[:, 1]),
            np.max(V[:, 2]),
        ])

        D_pos = np.sqrt(np.sum((V - ideal_pos) ** 2, axis=1))
        D_neg = np.sqrt(np.sum((V - ideal_neg) ** 2, axis=1))

        scores = D_neg / (D_pos + D_neg + 1e-10)

        best_idx = int(np.argmax(scores))
        return best_idx, scores.tolist()


    def add_flow(
        self,
        datapath,
        priority,
        match,
        actions,
        idle_timeout=0,
        hard_timeout=0,
    ):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        inst = [
            parser.OFPInstructionActions(
                ofproto.OFPIT_APPLY_ACTIONS, actions
            )
        ]
        mod = parser.OFPFlowMod(
            datapath=datapath,
            priority=priority,
            match=match,
            instructions=inst,
            idle_timeout=idle_timeout,
            hard_timeout=hard_timeout,
        )
        datapath.send_msg(mod)