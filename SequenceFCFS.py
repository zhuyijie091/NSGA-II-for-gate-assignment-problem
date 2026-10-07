import copy
import os
import time
from datetime import datetime
from typing import Tuple, List

from src.airport import Airport
from src.constrain_check import static_constrain_checker
from src.model.gate_graph import Flight
from src.util import flight_utils
from src.util.file import ExcelSave, write_txt
from src.util.draw_graph import plot_scatter
from src.util.utils import measure_execution_time

from heuristics_algorithm.NSGA2_S import (
    NSGA2_AGAP,
    Individual,
    convert_individual_to_fligths,
    save_individual,
    _gates,
    _gate_dict
)

class FCFS_AGAP(NSGA2_AGAP):
    """继承自NSGA2类以复用基础方法，并覆盖必要的方法"""

    def schedule_flights(self) -> List[Flight]:
        """核心调度逻辑"""
        # 按实际到达时间排序
        sorted_flights = sorted(
            copy.deepcopy(self.flights),
            key=lambda f: f.arrival_time
        )

        # 初始化各机位分配情况
        gate_allocations = {gate.gate.name: [] for gate in _gates}

        # 分配流程
        for flight in sorted_flights:
            for gg in _gates:  # 按预排序机位顺序遍历
                gate = gg.gate
                if not static_constrain_checker.check(gate, flight):
                    continue

                # 冲突检测
                if not any(flight_utils.is_overlapping(flight, f)
                           for f in gate_allocations[gate.name]):
                    flight.settle(gate.name)
                    gate_allocations[gate.name].append(flight)
                    break

        return sorted_flights

    def calculate_fitness(self, flights: List[Flight]) -> Tuple[float, float]:
        """覆盖父类方法，计算适应度"""
        # 靠桥率计算
        gate_usage_rate = Airport().get_boarding_bridge_usage_rate(flights)

        # 机型匹配度计算
        size_fit = 0.0
        for f in flights:
            if f.get_gate() is not None:
                gate_size = _gate_dict[f.get_gate()].gate.size
                if gate_size > 0:
                    size_fit += f.size / gate_size

        return (-gate_usage_rate, -size_fit)

@measure_execution_time
def run_fcfs() -> Tuple[List[List[Flight]], Individual, List[float]]:
    """执行FCFS算法主流程"""
    start_time = time.time()

    # 初始化算法
    fcfs = FCFS_AGAP()

    # 执行调度
    scheduled_flights = fcfs.schedule_flights()

    # 计算目标值
    gate_usage, size_fit = fcfs.calculate_fitness(scheduled_flights)

    # 构建模拟个体
    class Chromosome:
        def __init__(self, flights):
            self.gene = list(range(len(flights)))  # 伪基因序列

    best_indiv1 = Individual(
        chromosome=Chromosome(scheduled_flights),
        fitness=(gate_usage, size_fit),
        rank=0,
        crowding_distance=0.0
    )

    # 返回与遗传算法一致的数据结构
    execution_time = time.time() - start_time
    return [scheduled_flights], best_indiv1, [execution_time]

def save_fcfs_results(result: Tuple[List[List[Flight]], Individual, List[float]], time_consumed: float):
    """保存结果（完全复用遗传算法存储逻辑）"""
    final_population, best_indiv, iteration_time = result

    # 创建输出目录
    curr_path = os.path.dirname(os.path.abspath(__file__))
    curr_time = datetime.now().strftime("%Y_%m_%d-%H_%M_%S")
    result_path = f"{curr_path}/outputs-先到先得/{curr_time}/"
    os.makedirs(result_path, exist_ok=True)

    # 保存个体信息
    save_individual(best_indiv, result_path, time_consumed)

    # 写入参数信息
    write_txt(result_path, "参数", "算法类型: 先到先得")

    # 生成目标函数分布图（单点）
    plot_scatter(
        x=[-best_indiv.fitness[0]],
        y=[-best_indiv.fitness[1]],
        xlable="靠桥率",
        ylable="机型大小匹配值",
        title="算法结果",
        file_name="结果分布",
        save_path=result_path
    )

    # 生成收敛曲线占位数据
    ExcelSave().save_arr_data(
        arr_data=[[-best_indiv.fitness[0]]],
        save_path=result_path,
        file_name="靠桥率指标"
    )

    ExcelSave().save_arr_data(
        arr_data=[[-best_indiv.fitness[1]]],
        save_path=result_path,
        file_name="机型匹配指标"
    )

if __name__ == "__main__":
    # 执行算法，result包含(原始返回值, 执行时间)
    result, time_consumed = run_fcfs()
    final_population, best_indiv, time_info = result

    # 保存结果
    save_fcfs_results((final_population, best_indiv, time_info), time_consumed)

    # 输出验证信息
    scheduled_flights = final_population[0]
    unassigned = sum(1 for f in scheduled_flights if f.get_gate() is None)
    print(f"未分配航班数: {unassigned}")
    print(f"总耗时: {time_consumed:.2f}秒")