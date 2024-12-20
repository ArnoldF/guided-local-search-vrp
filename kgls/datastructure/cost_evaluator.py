import heapq
from collections import defaultdict
from itertools import cycle
import math

from .node import Node
from .edge import Edge
from .route import Route
from .vrp_solution import VRPSolution


class MaxHeapWithUpdate:
    def __init__(self, elements: list[Edge]):
        # Create a max-heap by inverting values (negate them)
        self.heap = elements
        heapq.heapify(self.heap)

    def get_max_element(self):
        # Pop the max element (the root of the heap)
        return heapq.heappop(self.heap)  # Removes the largest (smallest negative)

    def insert_element(self, element: Edge):
        # Add the new value (inverted for max-heap)
        heapq.heappush(self.heap, element)

    def get_sorted_list(self):
        # To get a sorted list, we retrieve and negate all elements
        return sorted([elem for elem in self.heap])


class CostEvaluator:

    def __init__(self, nodes: list[Node], capacity: int):
        self.nodes = nodes
        self._penalization_enabled: bool = False
        self._edge_penalties: dict[Edge, int] = defaultdict(int)
        self._baseline_cost: float = 0.0
        self._edge_ranking: MaxHeapWithUpdate = None
        self.neighborhood_size = 20
        self._capacity = capacity

        self._costs = dict()
        for node1 in nodes:
            self._costs[node1.node_id] = dict()
            for node2 in nodes:
                self._costs[node1.node_id][node2.node_id] = self._compute_euclidean_distance(node1, node2)

        self._penalized_costs = dict()
        for node1 in nodes:
            self._penalized_costs[node1.node_id] = dict()
            for node2 in nodes:
                self._penalized_costs[node1.node_id][node2.node_id] = self._costs[node1.node_id][node2.node_id]

        self.neighborhood, self._in_neighborhood_of = self._compute_neighborhood(nodes)
        self._nodes_to_update_for_relocation_chain: list[Node] = [
            node for node in nodes if not node.is_depot
        ]

        self._baseline_cost = int(sum(
            self.get_distance(node, other)
            for node in nodes
            if not node.is_depot
            for other in self.neighborhood[node]
        ) / (self.neighborhood_size * len(nodes)))

        self._penalization_criterium_options = cycle(["width", "length", "width_length"])
        self._penalization_criterium = next(self._penalization_criterium_options)

        self.ejection_costs = dict()
        self.insertion_costs = dict()
        self.insertion_after = dict()

    # def set_avg_distance(self, baseline_cost: float):
    #    self._baseline_cost: float = baseline_cost

    def update_ejection_costs(self, node):
        self.ejection_costs[node] = (
                self.get_distance(node, node.prev)
                + self.get_distance(node, node.next)
                - self.get_distance(node.prev, node.next)
        )

    @staticmethod
    def _compute_euclidean_distance(node1: Node, node2: Node) -> int:
        return round(
            math.sqrt(
                math.pow(node1.x_coordinate - node2.x_coordinate, 2) +
                math.pow(node1.y_coordinate - node2.y_coordinate, 2)
            )
        )

    def get_neighborhood(self, node: Node) -> list[Node]:
        return self.neighborhood[node]

    def _compute_neighborhood(self, nodes: list[Node]) -> list[Node]:
        neighborhood = {
            node: self._get_nearest_neighbors(node)
            for node in nodes
            if not node.is_depot
        }

        # compute the reverse datastructure
        in_neighborhood_of = {
            node: [other for other in neighborhood if node in neighborhood[other]]
            for node in nodes
            if not node.is_depot
        }

        return neighborhood, in_neighborhood_of

    def _get_nearest_neighbors(self, node: Node) -> list[Node]:
        sorted_distances_asc = sorted(self._costs[node.node_id].items(), key=lambda x: x[1], reverse=False)
        nearest_neighbors = [self.nodes[n] for (n, _) in sorted_distances_asc
                             if not self.nodes[n].is_depot and self.nodes[n] != node
                             ][:self.neighborhood_size]
        return nearest_neighbors

    def is_feasible(self, capacity: int) -> bool:
        return capacity <= self._capacity

    def _update_insertion_costs(self, node: Node, insert_next_to_node: Node):

        cost_insert_before = (
            self.get_distance(node, insert_next_to_node.prev)
            + self.get_distance(node, insert_next_to_node)
            - self.get_distance(insert_next_to_node.prev, insert_next_to_node)
        )
        cost_insert_after = (
            self.get_distance(node, insert_next_to_node.next)
            + self.get_distance(node, insert_next_to_node)
            - self.get_distance(insert_next_to_node, insert_next_to_node.next)
        )

        if cost_insert_before <= cost_insert_after:
            self.insertion_costs[node, insert_next_to_node] = cost_insert_before
            self.insertion_after[node, insert_next_to_node] = insert_next_to_node.prev
        else:
            self.insertion_costs[node, insert_next_to_node] = cost_insert_after
            self.insertion_after[node, insert_next_to_node] = insert_next_to_node

    def update_relocation_costs(self):
        for node in self._nodes_to_update_for_relocation_chain:
            self.update_ejection_costs(node)

            # if node is next to a depot, the insertion costs might need to be updated
            # if the neighbor is also next to a depot
            # TODO
            for potential_neighbour in self._in_neighborhood_of[node]:
                self._update_insertion_costs(node, potential_neighbour)

            # update the insertion costs of all nodes which could be inserted next to the node
            for potential_neighbour in self._in_neighborhood_of[node]:
                self._update_insertion_costs(potential_neighbour, node)

        self._nodes_to_update_for_relocation_chain = []

    def determine_edge_badness(self, routes: list[Route]):
        edges_in_solution: list[Edge] = []

        criterium_functions = {
            "length": self._compute_edge_length_value,
            "width": self._compute_edge_width_value,
            "width_length": self._compute_edge_width_length_value
        }
        # Get the computation function based on the current penalization criterium
        compute_edge_value = criterium_functions[self._penalization_criterium]

        for route in routes:
            center_x, center_y = (None, None)
            if self._penalization_criterium in {"width", "width_length"}:
                center_x, center_y = self._compute_route_center(route.get_nodes())

            for edge in route.get_edges():
                # Compute the value for the edge
                edge.value = compute_edge_value(edge, center_x, center_y, route)
                edge.value /= (1 + self._edge_penalties[edge])
                edges_in_solution.append(edge)

        # Update edge ranking
        self._edge_ranking = MaxHeapWithUpdate(edges_in_solution)

        # Rotate to next penalization criterium
        self._penalization_criterium = next(self._penalization_criterium_options)

    def _compute_edge_length_value(self, edge: Edge, *args) -> float:
        return self._costs[edge.nodes[0].node_id][edge.nodes[1].node_id]

    def _compute_edge_width_value(self, edge: Edge, center_x: float, center_y: float, route: Route) -> float:
        return self._compute_edge_width(edge, center_x, center_y, route.depot)

    def _compute_edge_width_length_value(self, edge: Edge, center_x: float, center_y: float, route: Route) -> float:
        width_value = self._compute_edge_width(edge, center_x, center_y, route.depot)
        length_value = self._costs[edge.nodes[0].node_id][edge.nodes[1].node_id]
        return width_value + length_value

    def enable_penalization(self):
        self._penalization_enabled = True
        self._nodes_to_update_for_relocation_chain = [
            node for node in self.neighborhood if not node.is_depot
        ]

    def disable_penalization(self):
        self._penalization_enabled = False
        self._nodes_to_update_for_relocation_chain = [
            node for node in self.neighborhood if not node.is_depot
        ]

    def get_distance(self, node1: Node, node2: Node) -> float:
        if not self._penalization_enabled:
            return self._costs[node1.node_id][node2.node_id]  # node1.get_distance(node2)
        else:
            return self._penalized_costs[node1.node_id][node2.node_id] # node1.get_distance(node2) + 0.1 * self._baseline_cost * self._edge_penalties[Edge(node1, node2)]

    def get_and_penalize_worst_edge(self) -> Edge:
        worst_edge = self._edge_ranking.get_max_element()
        self._edge_penalties[worst_edge] += 1

        # update costs
        node1 = worst_edge.nodes[0].node_id
        node2 = worst_edge.nodes[1].node_id
        penalization_costs = round(
                self._costs[node1][node2]
                + 0.1 * self._baseline_cost * self._edge_penalties[worst_edge]
        )
        self._penalized_costs[node1][node2] = penalization_costs
        self._penalized_costs[node2][node1] = penalization_costs

        # update (reduce) 'badness' of the just penalized edge (to avoid penalizing it again too soon)
        worst_edge.value = (
                self._costs[node1][node2]/
                (1 + self._edge_penalties[worst_edge])
        )
        self._edge_ranking.insert_element(worst_edge)

        # TODO here correct?
        if not worst_edge.get_first_node().is_depot:
            self._nodes_to_update_for_relocation_chain.append(worst_edge.get_first_node())
        if not worst_edge.get_second_node().is_depot:
            self._nodes_to_update_for_relocation_chain.append(worst_edge.get_second_node())

        return worst_edge

    def penalize(self, edge: Edge) -> None:
        self._edge_penalties[edge] += 1

    def get_solution_costs(self, solution: VRPSolution, ignore_penalties: bool = False) -> int:
        solution_costs: int = 0

        for route in solution.routes:
            if route.size > 0:
                cur_node = route.depot
                while not cur_node.next.is_depot:
                    if ignore_penalties:
                        solution_costs += self._costs[cur_node.node_id][cur_node.next.node_id]
                    else:
                        solution_costs += self.get_distance(cur_node, cur_node.next)
                    cur_node = cur_node.next

                if ignore_penalties:
                    solution_costs += self._costs[cur_node.node_id][cur_node.next.node_id]
                else:
                    solution_costs += self.get_distance(cur_node, cur_node.next)

        return solution_costs

    @staticmethod
    def _compute_edge_width(
            edge: Edge,
            route_center_x: float,
            route_center_y: float,
            depot: Node
    ) -> float:
        node1 = edge.get_first_node()
        node2 = edge.get_second_node()

        distance_depot_center = (
            math.sqrt(
                math.pow(depot.x_coordinate - route_center_x, 2) +
                math.pow(depot.y_coordinate - route_center_y, 2)
            )
        )

        distance_node1 = (
                (route_center_y - depot.y_coordinate) * node1.x_coordinate
                - (route_center_x - depot.x_coordinate) * node1.y_coordinate
                + (route_center_x * depot.y_coordinate) - (route_center_y * depot.x_coordinate)
        )
        distance_node1 = 0 if distance_depot_center == 0 else distance_node1 / distance_depot_center

        distance_node2 = (
                (route_center_y - depot.y_coordinate) * node2.x_coordinate
                - (route_center_x - depot.x_coordinate) * node2.y_coordinate
                + (route_center_x * depot.y_coordinate) - (route_center_y * depot.x_coordinate)
        )
        distance_node2 = 0 if distance_depot_center == 0 else distance_node2 / distance_depot_center

        return abs(distance_node1 - distance_node2)

    @staticmethod
    def _compute_route_center(nodes: list[Node]) -> tuple[float, float]:
        mean_x = sum(node.x_coordinate for node in nodes) / len(nodes)
        mean_y = sum(node.y_coordinate for node in nodes) / len(nodes)

        return mean_x, mean_y

