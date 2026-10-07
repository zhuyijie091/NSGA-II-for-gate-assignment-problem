import copy
import os
from datetime import datetime
from dataclasses import dataclass
from typing import Optional

from src.model.gate_graph import Flight
from src.airport import Airport
from src.constrain_check import static_constrain_checker
from src.util import flight_utils

# 复用原有的全局变量和工具函数
_near_gates = [gg for gg in Airport().get_gates() if Airport().is_near_gate(gg.gate.name)]
_remote_gates = [gg for gg in Airport().get_gates() if not Airport().is_near_gate(gg.gate.name)]
_gates = sorted(_near_gates + _remote_gates, key=lambda x: x.gate.distance_from_baggage_claim)
_gate_dict = {gg.gate.name: gg for gg in _gates}


class FCFS_AGAP:
    def __init__(self):
        self.flights = Airport().get_flights()
        self.gates = [gg.gate for gg in _gates]

    def schedule_flights(self) -> list[Flight]:
        """按实际到达时间排序进行机位分配"""
        # 按实际到达时间升序排序
        sorted_flights = sorted(
            copy.deepcopy(self.flights),  # 深度拷贝避免修改原始数据
            key=lambda f: f.scheduled_time.get_real_arrival_time()
        )

        # 初始化各机位已安排航班列表
        gate_assignments = {gate.gate.name: [] for gate in _gates}

        # 分配流程
        for flight in sorted_flights:
            for gg in _gates:  # 按预先排序的机位顺序遍历
                gate = gg.gate
                # 静态约束检查
                if not static_constrain_checker.check(gate, flight):
                    continue

                # 动态冲突检查
                conflict = False
                for assigned_flight in gate_assignments[gate.name]:
                    if flight_utils.is_overlapping(flight, assigned_flight):
                        conflict = True
                        break

                if not conflict:
                    flight.settle(gate.name)
                    gate_assignments[gate.name].append(flight)
                    break  # 分配成功后跳出机位循环

        return sorted_flights

    def calculate_fitness(self, flights: list[Flight]) -> tuple:
        """计算目标函数值（保持与遗传算法相同的指标）"""
        # 靠桥率计算
        gate_usage_rate = Airport().get_boarding_bridge_usage_rate(flights)

        # 机型匹配度计算
        size_fit = 0
        for f in flights:
            if f.get_gate() is not None:
                size_fit += f.size / _gate_dict[f.get_gate()].gate.size

        return (-gate_usage_rate, -size_fit)  # 保持负号方向一致性

    def calculate_gate_usage(self, flights):
        # 实现计算靠桥率的逻辑
        # 假设靠桥率是停靠在机位的航班数与总航班数的比例
        total_flights = len(flights)
        parked_flights = [f for f in flights if f.get_gate() is not None]
        gate_usage = len(parked_flights) / total_flights
        return gate_usage


@dataclass
class Individual:
    """模拟遗传算法的个体结构"""
    chromosome: object  # 为保持接口统一保留字段
    fitness: Optional[tuple]
    rank: Optional[int] = None
    crowding_distance: Optional[float] = None


def save_fcfs_result(result_flights: list[Flight], time_consumed: float):
    """保存结果（适配原有保存接口）"""

    # 构建模拟个体
    class TempChromosome:
        def __init__(self, flights):
            self.gene = [i for i, _ in enumerate(sorted(flights, key=lambda x: x.name))]

    best_indiv = Individual(
        chromosome=TempChromosome(result_flights),
        fitness=FCFS_AGAP().calculate_fitness(result_flights)
    )

    # 创建输出目录
    curr_path = os.path.dirname(os.path.abspath(__file__))
    curr_time = datetime.now().strftime("%Y_%m_%d-%H_%M_%S")
    result_path = f"{curr_path}/outputs-先到先得/{curr_time}/"
    os.makedirs(result_path, exist_ok=True)

    # 保存甘特图等信息（复用原有保存逻辑）
    obj_values = [0, 2]  # 与遗传算法显示相同指标
    Airport().save_scheduled_flights(
        scheduled_flights=result_flights,
        save_path=result_path,
        gantt_title="先到先得算法",
        additional_infor=[f"耗时: {time_consumed:.2f}s"],
        display_obj_value=obj_values
    )
    Airport().save_information(file_path=result_path)


def run_fcfs():
    """执行FCFS算法并保存结果"""
    import time
    start_time = time.time()

    scheduler = FCFS_AGAP()
    scheduled_flights = scheduler.schedule_flights()

    # 验证分配结果
    unassigned = [f for f in scheduled_flights if f.get_gate() is None]
    if len(unassigned) > 0:
        print(f"警告：{len(unassigned)}个航班未分配机位")

    # 保存结果
    save_fcfs_result(scheduled_flights, time.time() - start_time)


if __name__ == "__main__":
    run_fcfs()