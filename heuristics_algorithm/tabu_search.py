import copy
import os
from datetime import datetime
from dataclasses import dataclass
from random import random
from typing import Optional, Dict, List, Tuple

from heuristics_algorithm.NSGA2_S import assign_gate_to_flight
from src.model.gate_graph import Flight
from src.airport import Airport
from src.constrain_check import static_constrain_checker
from src.util import flight_utils

# 复用原有的全局变量和工具函数
_near_gates = [gg for gg in Airport().get_gates() if Airport().is_near_gate(gg.gate.name)]
_remote_gates = [gg for gg in Airport().get_gates() if not Airport().is_near_gate(gg.gate.name)]
_gates = sorted(_near_gates + _remote_gates, key=lambda x: x.gate.distance_from_baggage_claim)
_gate_dict = {gg.gate.name: gg for gg in _gates}

class TabuSearchAGAP:
    def __init__(self, max_iter=200, tabu_tenure=10, num_neighbors=100):
        self.flights = Airport().get_flights()
        self.max_iter = max_iter
        self.tabu_tenure = tabu_tenure
        self.num_neighbors = num_neighbors
        self.tabu_list = []
        self.best_solution = None
        self.history = {
            'gate_usage': [],
            'size_fit': [],
            'unassigned': []  # 新增未分配计数器
        }

    def generate_neighbors(self, solution: Dict) -> List[Dict]:
        """生成保证有效性的邻域解"""
        neighbors = []
        base_flights = solution['flights']

        for _ in range(self.num_neighbors):
            # 深拷贝当前解
            new_flights = [copy.deepcopy(f) for f in base_flights]

            # 随机交换两个航班的位置
            i, j = random.sample(range(len(new_flights)), 2)
            new_flights[i], new_flights[j] = new_flights[j], new_flights[i]

            # 重新分配机位
            assign_gate_to_flight(new_flights)

            # 跳过无效解
            if any(f.get_gate() is None for f in new_flights):
                continue

            neighbors.append({
                'flights': new_flights,
                'fitness': self.calculate_fitness(new_flights),
                'move': tuple(sorted((i, j)))
            })

        return neighbors

    def initialize_solution(self) -> Dict:
        """生成保证完全分配的初始解"""
        max_retry = 100  # 最大重试次数

        for _ in range(max_retry):
            # 深拷贝原始航班数据
            flights = [copy.deepcopy(f) for f in self.flights]

            # 随机排序
            random.shuffle(flights)
            assign_gate_to_flight(flights)

            # 验证全部分配成功
            if all(f.get_gate() is not None for f in flights):
                return {
                    'gene': [self.flights.index(orig_f) for orig_f in flights],
                    'flights': flights,
                    'fitness': self.calculate_fitness(flights)
                }

        raise RuntimeError("无法生成有效初始解，请检查约束条件或增加重试次数")

    def assign_gate_to_flight(flights: List[Flight]):
        """改进的机位分配逻辑"""
        gate_dict = {gg.gate.name: [] for gg in _gates}

        for f in flights:
            # 重置之前的分配
            f.reset()

            # 尝试分配近机位
            allocated = False
            for gg in _gates:
                if static_constrain_checker.check(gate=gg.gate, flight=f):
                    if not any(flight_utils.is_overlapping(f, parked_f)
                               for parked_f in gate_dict[gg.gate.name]):
                        gate_dict[gg.gate.name].append(f)
                        f.settle(gate_name=gg.gate.name)
                        allocated = True
                        break

            # 如果近机位分配失败，尝试远机位
            if not allocated:
                for gg in _remote_gates:
                    if static_constrain_checker.check(gate=gg.gate, flight=f):
                        if not any(flight_utils.is_overlapping(f, parked_f)
                                   for parked_f in gate_dict[gg.gate.name]):
                            gate_dict[gg.gate.name].append(f)
                            f.settle(gate_name=gg.gate.name)
                            allocated = True
                            break

            # 最终仍未分配的处理
            if not allocated:
                print(f"警告: 航班 {f.name} 未能分配机位")

        return gate_dict

    # 修改计算机型匹配度的代码
    def calculate_fitness(self, flights: List[Flight]) -> Tuple[float, float]:
        """带惩罚项的适应度计算"""
        valid_flights = [f for f in flights if f.get_gate() is not None]
        invalid_count = len(flights) - len(valid_flights)

        # 基础适应度
        gate_usage = Airport().get_boarding_bridge_usage_rate(valid_flights)
        size_fit = sum(f.size / _gate_dict[f.get_gate()].gate.size for f in valid_flights)

        # 添加惩罚项（未分配惩罚系数=10）
        penalty = invalid_count * 10
        return (-(gate_usage - penalty), -(size_fit - penalty))