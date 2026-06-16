from main_controller import BaseRoutingController
import networkx as nx
from itertools import islice


class StaticRoutingController(BaseRoutingController):

    ROUTING_MODE = "STATIC"

    def __init__(self, *args, **kwargs):
        super(StaticRoutingController, self).__init__(*args, **kwargs)

        self.static_path_table = {}

    def select_path(self, src, dst):
        key = (src, dst)

        if key in self.static_path_table:
            return self.static_path_table[key], []

        try:
            candidates = list(
                islice(
                    nx.shortest_simple_paths(
                        self.net,
                        src,
                        dst,
                        weight=None,    
                    ),
                    self.MAX_PATHS,
                )
            )

            if not candidates:
                self.logger.warning(
                    "[STATIC] Tidak ada path dari s%s ke s%s", src, dst
                )
                return [], []

            chosen = candidates[0]
            self.static_path_table[key] = chosen

            self.logger.info(
                "[STATIC] PATH DITETAPKAN s%s→s%s: %s",
                src, dst, chosen,
            )
            return chosen, []

        except nx.NetworkXNoPath:
            self.logger.warning(
                "[STATIC] Tidak ada path dari s%s ke s%s", src, dst
            )
            return [], []

        except Exception as e:
            self.logger.error("[STATIC] select_path error: %s", str(e))
            return [], []