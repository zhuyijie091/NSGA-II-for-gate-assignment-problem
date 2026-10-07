"""
    此模块负责静态约束的检查。

    该模块高度依赖属性值模块，属性值检查嘛，不知道属性值怎么检查。
"""

from abc import ABC, abstractmethod

from ..model.gate_graph import Gate, Flight

# 检查器
class ConstrainCheck(ABC):
    @abstractmethod
    def check(gate: Gate, flight: Flight) -> bool:
        pass


# 机位-机型机位容量约束
class _SizeCheck(ConstrainCheck):

    def check(self, gate: Gate, flight: Flight) -> bool:
        if flight.size <= gate.size:
            return True
        return False


# 机位-航司（可突破，但尽量不要出现）机位航司约束
class _AirlineCheck(ConstrainCheck):

    def check(self, gate: Gate, flight: Flight) -> bool:
        if isinstance(gate.airline, list):
            # 机位的列表为空代表没有航司偏好。count不等于0代表机位的航司偏好中包含该航班的航司。
            if len(gate.airline) == 0 or gate.airline.count(flight.airline) != 0:
                return True
        else:
            raise
        return False


# 机位-属性（国际国内）（可突破，但尽量不要出现）
class _InterORdomesticCheck(ConstrainCheck):

    def check(self, gate: Gate, flight: Flight) -> bool:
        if gate.inter_or_domestic >= flight.inter_or_domestic:
            return True
        return False
    

# 机位-任务（客货运）（可突破，但尽量不要出现）
class _PassengerORcargoCheck(ConstrainCheck):

    def check(self, gate: Gate, flight: Flight) -> bool:
        if gate.passenger_or_cargo >= flight.passenger_or_cargo:
            return True
        return False

#添加的新约束
class _AdjacentGateSizeCheck(ConstrainCheck):
    """检查相邻登机口的机型兼容性：若某登机口停放大型飞机，相邻登机口只能停放小型飞机"""
    def check(self, gate: Gate, flight: Flight) -> bool:
        # 假设size > 4为大型飞机（根据实际业务调整阈值）
        if flight.size <= 4:
            return True

        # _AdjacentGateSizeCheck.check()
        for adj_gate in gate.adjacent_gates:
            current_flight = adj_gate.assigned_flight
            if current_flight and current_flight.size > 4:
                return False
        return True


class _TaxiwayConflictCheck(ConstrainCheck):
    """滑行道动态冲突检查（时间窗口重叠）"""
    def check(self, gate: Gate, flight: Flight) -> bool:
        # 时间重叠阈值（15分钟）
        # _TaxiwayConflictCheck.check()
        TAU = 15 * 60  # 缓冲时间
        for allocated_flight in gate.taxiway_flights:
            # 检查时间窗口是否重叠（含缓冲）
            if (flight.arrival_time - TAU < allocated_flight.departure_time and
                    flight.departure_time + TAU > allocated_flight.arrival_time):
                return False
        return True


class _ElasticBufferCheck(ConstrainCheck):
    """弹性缓冲时间约束检查（单边必须满足最小间隔）"""

    def check(self, gate: Gate, flight: Flight) -> bool:
        # 缓冲时间阈值（30分钟）
        T = 30 * 60  # 转换为秒

        # 获取已分配航班并按到达时间排序
        scheduled_flights = sorted(gate.taxiway_flights, key=lambda x: x.arrival_time)

        # 寻找插入位置（二分查找优化）
        insert_pos = 0
        while insert_pos < len(scheduled_flights) and scheduled_flights[insert_pos].arrival_time < flight.arrival_time:
            insert_pos += 1

        # 明确获取前后航班
        prev = scheduled_flights[insert_pos - 1] if insert_pos > 0 else None
        next_flight = scheduled_flights[insert_pos] if insert_pos < len(scheduled_flights) else None

        # 检查前序航班间隔
        if prev and (flight.arrival_time - prev.departure_time) < T:
            return False

        # 检查后续航班间隔
        if next_flight and (next_flight.arrival_time - flight.departure_time) < T:
            return False

        return True


# 模块外调用此方法即可进行静态约束检查
def check(gate: Gate, flight: Flight) -> bool:
    """
    静态约束检查，通过则返回True，否则返回False
    """

    for checker in constarin_checker:
        # 有一条属性不通过，则返回False
        if not checker.check(gate, flight):
            return False
    # 全部通过，返回True
    return True


# constarin_checker = [
#     _AirlineCheck(),
#     _SizeCheck(),
#     _InterORdomesticCheck(),
#     _PassengerORcargoCheck()
#     # 上面新增一个检查器，则在这里增加其实例
# ]


# 修改检查器顺序，将_AirlineCheck移至最后
constarin_checker = [
    _SizeCheck(),
    _AdjacentGateSizeCheck(),
    _TaxiwayConflictCheck(),
    _ElasticBufferCheck(),
    _InterORdomesticCheck(),
    _PassengerORcargoCheck(),
    _AirlineCheck()  # 作为最后一道软约束
]
