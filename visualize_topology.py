from topology import PartialMeshTopo

import networkx as nx
import matplotlib.pyplot as plt


# LOAD TOPOLOGY

topo = PartialMeshTopo()

G = nx.Graph()


# NODES

for sw in topo.switches():
    G.add_node(
        sw,
        type="switch"
    )

for host in topo.hosts():
    G.add_node(
        host,
        type="host"
    )


# LINKS

for n1, n2 in topo.links():

    info = topo.linkInfo(n1, n2)

    bw = info.get("bw", 0)

    color = "gray"
    width = 0.5

    if n1.startswith("s") and n2.startswith("s"):

        if bw == 15:
            color = "green"
            width = 2

        elif bw == 10:
            color = "blue"
            width = 1.5

        elif bw == 5:
            color = "red"
            width = 1

    G.add_edge(
        n1,
        n2,
        bw=bw,
        color=color,
        width=width
    )


# POSISI SWITCH

rows = 5
cols = 6

switches = {}

switch_counter = 1

for r in range(rows):
    for c in range(cols):

        switches[(r, c)] = f"s{switch_counter}"

        switch_counter += 1


pos = {}

for r in range(rows):
    for c in range(cols):

        sw = switches[(r, c)]

        pos[sw] = (
            c * 4,
            -r * 4
        )


# POSISI HOST

host_map = {}

for host in topo.hosts():

    for n1, n2 in topo.links():

        if host == n1 and n2.startswith("s"):
            host_map.setdefault(n2, []).append(host)

        elif host == n2 and n1.startswith("s"):
            host_map.setdefault(n1, []).append(host)


for sw, hosts in host_map.items():

    sx, sy = pos[sw]

    left_side = sx == 0

    for i, host in enumerate(sorted(
        hosts,
        key=lambda h: int(h[1:])
    )):

        if left_side:

            pos[host] = (
                sx - 2,
                sy + (i - 5) * 0.3
            )

        else:

            pos[host] = (
                sx + 2,
                sy + (i - 5) * 0.3
            )


# COLORS

node_colors = []

for node in G.nodes():

    if G.nodes[node]["type"] == "switch":
        node_colors.append("lightblue")

    else:
        node_colors.append("orange")


edge_colors = [
    G[u][v]["color"]
    for u, v in G.edges()
]

edge_widths = [
    G[u][v]["width"]
    for u, v in G.edges()
]


# DRAW NODES

plt.figure(figsize=(22, 12))

nx.draw_networkx_nodes(
    G,
    pos,
    node_color=node_colors,
    node_size=800
)

nx.draw_networkx_edges(
    G,
    pos,
    edge_color=edge_colors,
    width=edge_widths
)


# LABEL SWITCH

switch_labels = {
    n: n
    for n in topo.switches()
}

nx.draw_networkx_labels(
    G,
    pos,
    labels=switch_labels,
    font_size=15
)


# HOST GROUP LABEL

host_group_labels = {}

for sw, hosts in host_map.items():

    hosts = sorted(
        hosts,
        key=lambda h: int(h[1:])
    )

    first_host = hosts[0]
    last_host = hosts[-1]

    host_group_labels[sw] = (
        f"{first_host}-{last_host}"
    )


host_label_pos = {}

for sw in host_group_labels:

    sx, sy = pos[sw]

    if sx == 0:

        host_label_pos[sw] = (
            sx - 3.5,
            sy
        )

    else:

        host_label_pos[sw] = (
            sx + 3.5,
            sy
        )


nx.draw_networkx_labels(
    G,
    host_label_pos,
    labels=host_group_labels,
    font_size=20,
    font_color="darkred"
)


# LINK LABELS

edge_labels = {}

for u, v in G.edges():

    if (
        G.nodes[u]["type"] == "switch"
        and
        G.nodes[v]["type"] == "switch"
    ):

        edge_labels[(u, v)] = (
            f"{G[u][v]['bw']} Mbps"
        )


nx.draw_networkx_edge_labels(
    G,
    pos,
    edge_labels=edge_labels,
    font_size=12
)


# OUTPUT

plt.title(
    "SDN Partial Mesh Topology\n"
    "Green=15Mbps | Blue=10Mbps | Red=5Mbps"
)

plt.axis("off")

plt.tight_layout()

plt.savefig(
    "topology.png",
    dpi=300,
    bbox_inches="tight"
)

plt.show()