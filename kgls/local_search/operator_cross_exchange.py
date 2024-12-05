import logging

from kgls.datastructure import Node, Route, VRPSolution, CostEvaluator

logger = logging.getLogger(__name__)


class CrossExchange:

    def __init__(
            self,
            segment1: list[Node],
            segment2: list[Node],
            segment1_insert_after: Node,
            segment2_insert_after: Node,
            improvement: float,
            start_node: Node
    ):
        self.segment1 = segment1
        self.segment2 = segment2
        self.segment1_insert_after = segment1_insert_after
        self.segment2_insert_after = segment2_insert_after
        self.start_node = start_node

        self.improvement = improvement

    def __lt__(self, other):
        return self.improvement > other.improvement

    def get_routes(self) -> list[Route]:
        return set([self.segment1[0].route, self.segment2[0].route])

    def is_disjunct(self, other):
        # TODO improve?
        if self.segment1[0].route in [other.segment1[0].route, other.segment2[0].route]:
            return False
        if self.segment2[0].route in [other.segment1[0].route, other.segment2[0].route]:
            return False

        return True

    def execute(self, solution: VRPSolution):
        logger.debug(f'Executing cross-exchange with segments of sizes '
                     f'{len(self.segment1)} and {len(self.segment2)} '
                     f'with improvement of {int(self.improvement)}')

        solution.remove_nodes(self.segment1)
        solution.remove_nodes(self.segment2)

        solution.insert_nodes_after(self.segment1, self.segment1_insert_after)
        solution.insert_nodes_after(self.segment2, self.segment2_insert_after)


def search_cross_exchanges_from(
        cost_evaluator: CostEvaluator,
        start_node: Node,
        segment1_directions: list[int] = [0, 1],
        segment2_directions: list[int] = [0, 1]
) -> list[CrossExchange]:
    # try to exchange a node segment starting with start_node (and extending it into 'direction')
    # with a segment from another route, starting from a neighborhood node of 'start_node'
    route1: Route = start_node.route
    candidate_moves: list[CrossExchange] = []

    for segment1_direction in segment1_directions:
        for segment2_direction in segment2_directions:

            if segment1_direction == 1:
                route1_segment_connection_start = start_node.prev
            else:
                route1_segment_connection_start = start_node.next

            for route2_segment_connection_start in cost_evaluator.get_neighborhood(start_node):
                if route2_segment_connection_start.route != start_node.route:
                    # compute improvement of first cross
                    # TODO can go both directions
                    segment2_start = route2_segment_connection_start.get_neighbour(segment2_direction)
                    if segment2_start.is_depot:
                        continue

                    # current edges - new edges
                    improvement_first_cross = (
                            cost_evaluator.get_distance(start_node, route1_segment_connection_start)
                            + cost_evaluator.get_distance(segment2_start, route2_segment_connection_start)
                            - cost_evaluator.get_distance(start_node, route2_segment_connection_start)
                            - cost_evaluator.get_distance(segment2_start, route1_segment_connection_start)
                    )

                    if improvement_first_cross > 0:
                        segment1_end = start_node
                        segment1_list = [segment1_end]
                        segment1_volume = segment1_end.demand

                        route2 = route2_segment_connection_start.route

                        # try to extend segment 1 until the end
                        while not segment1_end.is_depot:
                            # extend segment2 until capacity of route 1 is violated
                            segment2_end = segment2_start
                            segment2_list = [segment2_end]
                            segment2_volume = segment2_end.demand

                            while (not segment2_end.is_depot and
                                   cost_evaluator.is_feasible(route1.volume - segment1_volume + segment2_volume)):

                                # check feasibility of route 2
                                if cost_evaluator.is_feasible(route2.volume - segment2_volume + segment1_volume):
                                    # check overall improvement of move
                                    route1_segment_connection_end = segment1_end.get_neighbour(segment1_direction)
                                    route2_segment_connection_end = segment2_end.get_neighbour(segment2_direction)

                                    improvement_second_cross = (
                                        cost_evaluator.get_distance(segment1_end, route1_segment_connection_end)
                                        + cost_evaluator.get_distance(segment2_end, route2_segment_connection_end)
                                        - cost_evaluator.get_distance(segment1_end, route2_segment_connection_end)
                                        - cost_evaluator.get_distance(segment2_end, route1_segment_connection_end)
                                    )
                                    improvement = improvement_first_cross + improvement_second_cross

                                    if improvement > 0:
                                        # store move
                                        candidate_moves.append(
                                            CrossExchange(
                                                segment1_list.copy(),
                                                segment2_list.copy(),
                                                route2_segment_connection_start if segment2_direction == 1 else route2_segment_connection_end,
                                                route1_segment_connection_start if segment1_direction == 1 else route1_segment_connection_end,
                                                improvement,
                                                start_node
                                            )
                                        )

                                # extend segment2
                                # segment lists are in the order as the nodes are later inserted
                                segment2_end = segment2_end.get_neighbour(segment2_direction)
                                if (segment2_direction == 1 and segment1_direction == 0) or (segment1_direction + segment2_direction == 0):
                                    segment2_list.insert(0, segment2_end)
                                else:
                                    segment2_list.append(segment2_end)
                                segment2_volume += segment2_end.demand

                            # extend segment1
                            segment1_end = segment1_end.get_neighbour(segment1_direction)
                            if (segment1_direction == 1 and segment2_direction == 0) or (segment1_direction + segment2_direction == 0):
                                segment1_list.insert(0, segment1_end)
                            else:
                                segment1_list.append(segment1_end)

                            segment1_volume += segment1_end.demand

    return candidate_moves


def search_cross_exchanges(
        cost_evaluator: CostEvaluator,
        start_nodes: list[Node],
) -> list[CrossExchange]:
    candidate_moves = []
    for start_node in start_nodes:
        candidate_moves.extend(
            search_cross_exchanges_from(cost_evaluator, start_node)
        )

    return sorted(candidate_moves)