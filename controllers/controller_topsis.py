from main_controller import BaseRoutingController


class TopsisRoutingController(BaseRoutingController):

    ROUTING_MODE = "TOPSIS"

    def select_path(self, src, dst):
        paths = self._get_k_paths(src, dst)

        if not paths:
            self.logger.warning(
                "[TOPSIS] Tidak ada path dari s%s ke s%s", src, dst
            )
            return [], []

        if len(paths) == 1:
            return paths[0], [1.0]

        matrix = []
        for path in paths:
            m = self.calculate_path_metric(path)
            matrix.append([m["bw"], m["delay"], m["loss"]])

            self.logger.debug(
                "[TOPSIS] PATH=%s  bw=%.2f  delay=%.2f ms  loss=%.4f%%",
                path, m["bw"], m["delay"], m["loss"],
            )

        best_idx, topsis_scores = self._topsis(matrix)

        self.logger.info("=" * 45)
        self.logger.info("[TOPSIS] src=s%s dst=s%s", src, dst)
        self.logger.info("-" * 45)
        for i, (path, score) in enumerate(zip(paths, topsis_scores)):
            m = self.calculate_path_metric(path)
            marker = " ← SELECTED" if i == best_idx else ""
            self.logger.info(
                "  PATH %d | score=%.4f | bw=%.2f Mbps | "
                "delay=%.2f ms | loss=%.4f%%%s",
                i + 1, score, m["bw"], m["delay"], m["loss"], marker
            )
        self.logger.info("=" * 45)

        best_path = paths[best_idx]

        # self.logger.info(
        #     "[TOPSIS] BEST PATH=%s  score=%.4f  (dari %d kandidat)",
        #     best_path,
        #     topsis_scores[best_idx] if topsis_scores else 0.0,
        #     len(paths),
        # )

        return best_path, topsis_scores