from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional
import uuid


class StrategyType(str, Enum):
    SHORT_PUT = "Short Put"
    SHORT_CALL = "Short Call"
    SHORT_STRANGLE = "Short Strangle"
    SHORT_STRADDLE = "Short Straddle"
    BULL_PUT_SPREAD = "Bull Put Spread"
    BEAR_CALL_SPREAD = "Bear Call Spread"
    IRON_CONDOR = "Iron Condor"


class StrategyStatus(str, Enum):
    ACTIVE = "Active"
    PAUSED = "Paused"


@dataclass
class StrategyConfig:
    name: str
    strategy_type: StrategyType
    underlyings: List[str]

    # DTE window
    dte_min: int = 30
    dte_max: int = 60
    dte_exit: int = 21           # close at or below this DTE

    # Delta targets (absolute value)
    delta_target: float = 0.30
    delta_tolerance: float = 0.05
    put_delta_target: float = 0.30
    call_delta_target: float = 0.30

    # Spread width (for spreads / condors, in dollars)
    wing_width: float = 5.0

    # Sizing
    max_contracts: int = 1
    max_positions_per_underlying: int = 1

    # Risk limits
    max_risk_per_trade: float = 5000.0   # dollars
    max_total_risk: float = 20000.0      # dollars across all positions in this strategy

    # Exit rules
    stop_loss_pct: float = 2.0           # close when loss = stop_loss_pct × credit (e.g. 2.0 = 200%)
    profit_target_pct: float = 0.50      # close when profit = profit_target_pct × credit

    # Entry filters
    min_premium: float = 0.50            # minimum credit to collect (per share)
    min_iv_rank: Optional[float] = None
    max_iv_rank: Optional[float] = None

    # Engine behaviour
    enabled: bool = True
    dry_run: bool = False                # simulate orders, don't submit
    scan_interval_minutes: int = 5

    # Metadata
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: StrategyStatus = StrategyStatus.ACTIVE

    # ------------------------------------------------------------------ #

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "strategy_type": self.strategy_type.value,
            "underlyings": self.underlyings,
            "dte_min": self.dte_min,
            "dte_max": self.dte_max,
            "dte_exit": self.dte_exit,
            "delta_target": self.delta_target,
            "delta_tolerance": self.delta_tolerance,
            "put_delta_target": self.put_delta_target,
            "call_delta_target": self.call_delta_target,
            "wing_width": self.wing_width,
            "max_contracts": self.max_contracts,
            "max_positions_per_underlying": self.max_positions_per_underlying,
            "max_risk_per_trade": self.max_risk_per_trade,
            "max_total_risk": self.max_total_risk,
            "stop_loss_pct": self.stop_loss_pct,
            "profit_target_pct": self.profit_target_pct,
            "min_premium": self.min_premium,
            "min_iv_rank": self.min_iv_rank,
            "max_iv_rank": self.max_iv_rank,
            "enabled": self.enabled,
            "dry_run": self.dry_run,
            "scan_interval_minutes": self.scan_interval_minutes,
            "status": self.status.value,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "StrategyConfig":
        return cls(
            id=d.get("id", str(uuid.uuid4())),
            name=d["name"],
            strategy_type=StrategyType(d["strategy_type"]),
            underlyings=d["underlyings"],
            dte_min=d.get("dte_min", 30),
            dte_max=d.get("dte_max", 60),
            dte_exit=d.get("dte_exit", 21),
            delta_target=d.get("delta_target", 0.30),
            delta_tolerance=d.get("delta_tolerance", 0.05),
            put_delta_target=d.get("put_delta_target", 0.30),
            call_delta_target=d.get("call_delta_target", 0.30),
            wing_width=d.get("wing_width", 5.0),
            max_contracts=d.get("max_contracts", 1),
            max_positions_per_underlying=d.get("max_positions_per_underlying", 1),
            max_risk_per_trade=d.get("max_risk_per_trade", 5000.0),
            max_total_risk=d.get("max_total_risk", 20000.0),
            stop_loss_pct=d.get("stop_loss_pct", 2.0),
            profit_target_pct=d.get("profit_target_pct", 0.50),
            min_premium=d.get("min_premium", 0.50),
            min_iv_rank=d.get("min_iv_rank"),
            max_iv_rank=d.get("max_iv_rank"),
            enabled=d.get("enabled", True),
            dry_run=d.get("dry_run", False),
            scan_interval_minutes=d.get("scan_interval_minutes", 5),
            status=StrategyStatus(d.get("status", StrategyStatus.ACTIVE.value)),
        )
