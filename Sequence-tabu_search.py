import random
import time
import os
from datetime import datetime
from typing import List, Tuple, Dict
from copy import deepcopy

from src.airport import Airport
from src.constrain_check import static_constrain_checker
from src.model.gate_graph import Flight
from src.util.file import ExcelSave, write_txt
from src.util.draw_graph import plot_scatter
from src.util.utils import measure_execution_time
from src.util import flight_utils

# 复用原有全局变量和函数
_near_gates = [gg for gg in Airport().get_gates() if Airport().is_near_gate(gg.gate.name)]
_remote_gates = [gg for gg in Airport().get_gates() if not Airport().is_near_gate(gg.gate.name)]
_gates = sorted(_near_gates + _remote_gates, key=lambda x: x.gate.distance_from_baggage_claim)
_gate_dict = {gg.gate.name: gg for gg in _gates}


def assign_gate_to_flight(flights: List[Flight]):
    """航班分配机位逻辑（复用原有实现）"""
    gate_dict = {gg.gate.name: [] for gg in _gates}
    for f in flights:
        for gg in _gates:
            if static_constrain_checker.check(gate=gg.gate, flight=f):
                if not any(flight_utils.is_overlapping(f, parked_f) for parked_f in gate_dict[gg.gate.name]):
                    gate_dict[gg.gate.name].append(f)
                    f.settle(gate_name=gg.gate.name)
                    break
    return gate_dict


class TabuSearchAGAP:
    def __init__(self, max_iter=100, tabu_tenure=7, num_neighbors=50):
        self.flights = Airport().get_flights()
        self.max_iter = max_iter
        self.tabu_tenure = tabu_tenure
        self.num_neighbors = num_neighbors
        self.tabu_list = []
        self.best_solution = None
        self.history = {
            'fitness': [],
            'best_fitness': [],
            'gate_usage': [],
            'size_fit': [],
            'iteration_time': []
        }

    def initialize_solution(self) -> Dict:
        """生成初始解"""
        gene = list(range(len(self.flights)))
        random.shuffle(gene)
        flights = [self.flights[i] for i in gene]
        assign_gate_to_flight(flights)
        return {
            'gene': gene,
            'flights': flights,
            'fitness': self.calculate_fitness(flights)
        }

    def calculate_fitness(self, flights: List[Flight]) -> Tuple[float, float]:
        """计算双目标适应度"""
        gate_usage = Airport().get_boarding_bridge_usage_rate(flights)
        size_fit = sum(f.size / _gate_dict[f.get_gate()].gate.size for f in flights if f.get_gate())
        return (-gate_usage, -size_fit)  # 负号用于最小化

    def generate_neighbors(self, solution: Dict) -> List[Dict]:
        """生成邻域解"""
        neighbors = []
        base_gene = solution['gene']
        for _ in range(self.num_neighbors):
            i, j = random.sample(range(len(base_gene)), 2)
            new_gene = base_gene.copy()
            new_gene[i], new_gene[j] = new_gene[j], new_gene[i]

            if tuple(sorted((i, j))) in self.tabu_list:
                continue

            new_flights = [self.flights[idx] for idx in new_gene]
            assign_gate_to_flight(new_flights)
            neighbors.append({
                'gene': new_gene,
                'flights': new_flights,
                'fitness': self.calculate_fitness(new_flights),
                'move': tuple(sorted((i, j)))
            })
        return neighbors

    def update_tabu_list(self, move: Tuple[int, int]):
        """更新禁忌表"""
        self.tabu_list.append(move)
        if len(self.tabu_list) > self.tabu_tenure:
            self.tabu_list.pop(0)

    @measure_execution_time
    def run(self) -> Dict:
        """主算法流程"""
        current = self.initialize_solution()
        self.best_solution = deepcopy(current)
        self._update_history(current, 0)

        for iter in range(self.max_iter):
            start_time = time.time()

            # 生成并评估邻域
            neighbors = self.generate_neighbors(current)
            if not neighbors:
                break

            # 选择最优候选解
            best_candidate = min(neighbors, key=lambda x: x['fitness'])

            # 更新当前解
            current = best_candidate
            self.update_tabu_list(best_candidate['move'])

            # 更新全局最优
            if self._is_dominated(best_candidate['fitness'], self.best_solution['fitness']):
                self.best_solution = deepcopy(best_candidate)

            # 记录迭代信息
            self._update_history(current, time.time() - start_time)
            print(f"Iter {iter + 1}: Best Fitness {self.best_solution['fitness']}")

        return self.best_solution

    def _is_dominated(self, fit1: Tuple, fit2: Tuple) -> bool:
        """支配关系判断"""
        return all(f1 <= f2 for f1, f2 in zip(fit1, fit2)) and any(f1 < f2 for f1, f2 in zip(fit1, fit2))

    def _update_history(self, solution: Dict, iter_time: float):
        """记录历史数据"""
        gate_usage, size_fit = solution['fitness']
        self.history['fitness'].append((gate_usage, size_fit))
        self.history['gate_usage'].append(-gate_usage)
        self.history['size_fit'].append(-size_fit)
        self.history['iteration_time'].append(iter_time)
        if self.history['best_fitness']:
            prev_best = self.history['best_fitness'][-1]
            new_best = min(prev_best, solution['fitness'], key=lambda x: x[0] + x[1])
            self.history['best_fitness'].append(new_best)
        else:
            self.history['best_fitness'].append(solution['fitness'])

    def save_results(self, best_solution: Dict, time_consumed: float):
        """结果保存方法"""
        curr_path = os.path.dirname(os.path.abspath(__file__))
        curr_time = datetime.now().strftime("%Y%m%d-%H%M%S")
        save_path = f"{curr_path}/outputs-tabu_search/{curr_time}/"
        os.makedirs(save_path, exist_ok=True)

        # 保存航班分配结果
        Airport().save_scheduled_flights(
            best_solution['flights'],
            save_path,
            "禁忌搜索算法",
            [f"总耗时: {time_consumed:.2f}s"],
            display_obj_value=[0, 1]
        )

        # 保存收敛曲线
        iterations = list(range(len(self.history['gate_usage'])))
        plot_scatter(
            x=iterations, y=self.history['gate_usage'],
            xlable="Iteration", ylable="Boarding Bridge Usage",
            title="靠桥率收敛图", file_name="gate_usage", save_path=save_path
        )
        plot_scatter(
            x=iterations, y=self.history['size_fit'],
            xlable="Iteration", ylable="Size Fitness",
            title="机型匹配收敛图", file_name="size_fit", save_path=save_path
        )

        # 保存参数
        write_txt(
            save_path, "parameters",
            f"Max Iter: {self.max_iter}\nTabu Tenure: {self.tabu_tenure}\nNeighbors: {self.num_neighbors}"
        )


if __name__ == "__main__":
    # 算法参数设置
    ts = TabuSearchAGAP(
        max_iter=200,
        tabu_tenure=10,
        num_neighbors=100
    )

    # 运行算法
    best_sol, exec_time = ts.run()

    # 保存结果
    ts.save_results(best_sol, exec_time)