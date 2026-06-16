from main_controller import BaseRoutingController
import networkx as nx


class ShortestPathController(BaseRoutingController):

    ROUTING_MODE = "SHORTEST_PATH"

    def select_path(self, src, dst):
        try:
            path = nx.shortest_path(
                self.net,
                src,
                dst,
                weight=None,
            )
            return path, []

        except nx.NetworkXNoPath:
            self.logger.warning(
                "[SP] Tidak ada path dari s%s ke s%s", src, dst
            )
            return [], []

        except Exception as e:
            self.logger.error("[SP] select_path error: %s", str(e))
            return [], []