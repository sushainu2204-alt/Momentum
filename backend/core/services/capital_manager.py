"""
Capital Manager Service

Manages capital allocation and risk limits using Zerodha margins API.
- Query Kite for real-time capital (source of truth)
- Cache margins data (2-second cache)
- Enforce position limits
- Calculate position sizes
- Manage risk per trade
- Background sync to DB for historical tracking
"""

from typing import Optional, Dict, Any
from datetime import date, datetime
from dataclasses import dataclass
import logging

from backend.core.services.position_manager import PositionManager
from backend.infrastructure.database.base import IDatabase

logger = logging.getLogger(__name__)


@dataclass
class TradingLimits:
    """Trading limits configuration"""
    starting_capital: float = 100000  # ₹1,00,000
    max_positions: int = 5
    position_size_pct: float = 20  # Max 20% per trade
    risk_per_trade_pct: float = 2  # Max 2% risk per trade
    max_capital_at_risk_pct: float = 10  # Max 10% total risk


class CapitalManager:
    """
    Manages capital and enforces risk limits using Zerodha margins API.
    
    Architecture (Hybrid):
    - Runtime: Query Kite margins API directly (source of truth)
    - Caching: 2-second cache to reduce API calls
    - Database: Historical records and audit trail
    - Background: Periodic sync to DB
    
    Responsibilities:
    - Query real-time capital from Kite
    - Calculate position sizes
    - Enforce max positions limit
    - Enforce capital allocation limits
    - Track total risk
    """
    
    def __init__(
        self,
        database: IDatabase,
        kite_service: Any,  # KiteService instance
        position_manager: PositionManager,
        limits: Optional[TradingLimits] = None
    ):
        self.db = database
        self.kite = kite_service
        self.position_manager = position_manager
        self.limits = limits or TradingLimits()
        
        # 2-second cache for margins
        self._margins_cache: Optional[Dict] = None
        self._cache_timestamp: Optional[datetime] = None
    
    # ================================================================
    # CAPITAL TRACKING (KITE API - SOURCE OF TRUTH)
    # ================================================================
    
    async def get_available_capital(self) -> float:
        """
        Get available capital for new trades from Kite margins API.
        
        Uses: equity.available.cash + equity.available.collateral
        
        Returns:
            Available capital amount (free cash + collateral)
        """
        try:
            margins = await self._get_kite_margins_cached()
            
            if margins and 'equity' in margins:
                equity = margins['equity']
                available = equity.get('available', {})
                
                # Free cash + collateral (for intraday trading)
                cash = available.get('cash', 0.0)
                collateral = available.get('collateral', 0.0)
                
                available_capital = cash + collateral
                
                logger.debug(
                    f"Available capital from Kite: ₹{available_capital:,.2f} "
                    f"(Cash: ₹{cash:,.2f}, Collateral: ₹{collateral:,.2f})"
                )
                
                return available_capital
            
            # Fallback to DB if Kite fails
            logger.warning("Kite margins unavailable, using DB fallback")
            state = await self._get_capital_state()
            if state:
                return state['available_capital']
            
            return self.limits.starting_capital
            
        except Exception as e:
            logger.error(f"Error getting available capital: {e}")
            # Fallback to DB
            state = await self._get_capital_state()
            if state:
                return state['available_capital']
            return self.limits.starting_capital
    
    async def get_current_capital(self) -> float:
        """
        Get current total capital from Kite margins API.
        
        Uses: equity.net (net available + utilized)
        
        Returns:
            Current capital
        """
        try:
            margins = await self._get_kite_margins_cached()
            
            if margins and 'equity' in margins:
                equity = margins['equity']
                
                # Net = available + utilized (current total)
                net = equity.get('net', 0.0)
                
                if net > 0:
                    logger.debug(f"Current capital from Kite: ₹{net:,.2f}")
                    return net
            
            # Fallback to DB
            logger.warning("Kite margins unavailable, using DB fallback")
            state = await self._get_capital_state()
            if state:
                return state['current_capital']
            
            return self.limits.starting_capital
            
        except Exception as e:
            logger.error(f"Error getting current capital: {e}")
            state = await self._get_capital_state()
            if state:
                return state['current_capital']
            return self.limits.starting_capital
    
    async def get_utilized_margin(self) -> float:
        """
        Get utilized margin from Kite.
        
        Returns:
            Amount of margin currently used
        """
        try:
            margins = await self._get_kite_margins_cached()
            
            if margins and 'equity' in margins:
                equity = margins['equity']
                utilised = equity.get('utilised', {})
                
                # Total debits (margin used)
                debits = utilised.get('debits', 0.0)
                
                logger.debug(f"Utilized margin from Kite: ₹{debits:,.2f}")
                return debits
            
            return 0.0
            
        except Exception as e:
            logger.error(f"Error getting utilized margin: {e}")
            return 0.0
    
    async def can_allocate(self, required_capital: float) -> bool:
        """
        Check if we can allocate capital for a new position.
        
        Args:
            required_capital: Capital needed for position
        
        Returns:
            True if capital available
        """
        available = await self.get_available_capital()
        
        # Check if we have enough capital
        if required_capital > available:
            logger.warning(
                f"Insufficient capital: Need ₹{required_capital:.2f}, "
                f"Available: ₹{available:.2f}"
            )
            return False
        
        # Check position size limit (max 20% per trade)
        current_capital = await self.get_current_capital()
        max_per_trade = current_capital * (self.limits.position_size_pct / 100)
        
        if required_capital > max_per_trade:
            logger.warning(
                f"Position too large: ₹{required_capital:.2f} > "
                f"Max ₹{max_per_trade:.2f} ({self.limits.position_size_pct}%)"
            )
            return False
        
        return True
    
    # ================================================================
    # POSITION SIZING
    # ================================================================
    
    async def calculate_position_size(
        self,
        entry_price: float,
        stop_loss: float,
        risk_pct: Optional[float] = None
    ) -> int:
        """
        Calculate position size based on risk.
        
        Args:
            entry_price: Entry price per share
            stop_loss: Stop loss price
            risk_pct: Risk percentage (default: from limits)
        
        Returns:
            Number of shares to buy
        """
        try:
            current_capital = await self.get_current_capital()
            risk_percent = risk_pct or self.limits.risk_per_trade_pct
            
            # Calculate risk amount
            risk_amount = current_capital * (risk_percent / 100)
            
            # Calculate SL distance
            sl_distance = abs(entry_price - stop_loss)
            
            if sl_distance == 0:
                logger.warning("Stop loss equals entry price - using 1% default")
                sl_distance = entry_price * 0.01
            
            # Calculate quantity: risk_amount / sl_distance
            quantity = int(risk_amount / sl_distance)
            
            # Ensure minimum 1 share
            quantity = max(1, quantity)
            
            # Check position size limit
            position_value = quantity * entry_price
            max_position_value = current_capital * (self.limits.position_size_pct / 100)
            
            if position_value > max_position_value:
                # Adjust quantity to fit position size limit
                quantity = int(max_position_value / entry_price)
                quantity = max(1, quantity)
            
            logger.debug(
                f"Position size calculated: {quantity} shares @ ₹{entry_price:.2f}, "
                f"Risk: ₹{risk_amount:.2f} ({risk_percent}%), "
                f"SL Distance: ₹{sl_distance:.2f}"
            )
            
            return quantity
            
        except Exception as e:
            logger.error(f"Error calculating position size: {e}")
            # Fallback: Calculate based on max position size
            current_capital = await self.get_current_capital()
            max_position_value = current_capital * (self.limits.position_size_pct / 100)
            return max(1, int(max_position_value / entry_price))
    
    # ================================================================
    # RISK MANAGEMENT
    # ================================================================
    
    async def check_position_limit(self) -> bool:
        """
        Check if we can open another position.
        
        Returns:
            True if below position limit
        """
        current_positions = await self.position_manager.get_open_positions_count()
        
        if current_positions >= self.limits.max_positions:
            logger.warning(
                f"Max positions reached: {current_positions}/{self.limits.max_positions}"
            )
            return False
        
        return True
    
    async def get_total_risk(self) -> float:
        """
        Calculate total capital at risk (sum of SL distances).
        
        Returns:
            Total risk amount
        """
        try:
            # Get open positions from DB
            from backend.infrastructure.database.position_repository import PositionRepository
            position_repo = PositionRepository(self.db)
            
            db_positions = await position_repo.get_open_positions()
            
            total_risk = 0.0
            for pos in db_positions:
                risk = abs(pos['entry_price'] - pos['stop_loss']) * pos['quantity']
                total_risk += risk
            
            return total_risk
            
        except Exception as e:
            logger.error(f"Error calculating total risk: {e}")
            return 0.0
    
    async def check_risk_limit(self, additional_risk: float) -> bool:
        """
        Check if adding position would exceed risk limit.
        
        Args:
            additional_risk: Risk from new position
        
        Returns:
            True if within risk limits
        """
        current_risk = await self.get_total_risk()
        total_risk = current_risk + additional_risk
        
        current_capital = await self.get_current_capital()
        max_risk = current_capital * (self.limits.max_capital_at_risk_pct / 100)
        
        if total_risk > max_risk:
            logger.warning(
                f"Risk limit exceeded: ₹{total_risk:.2f} > ₹{max_risk:.2f} "
                f"({self.limits.max_capital_at_risk_pct}%)"
            )
            return False
        
        return True
    
    # ================================================================
    # KITE API INTEGRATION (WITH CACHING)
    # ================================================================
    
    async def _get_kite_margins_cached(self) -> Optional[Dict]:
        """
        Get margins from Kite with 2-second caching.
        
        Returns:
            Margins data from Kite API
        """
        try:
            # Check cache validity (2 seconds)
            if self._margins_cache and self._cache_timestamp:
                age = (datetime.now() - self._cache_timestamp).total_seconds()
                if age < 2:
                    logger.debug("Using cached margins data")
                    return self._margins_cache
            
            # Fetch from Kite
            logger.debug("Fetching margins from Kite API")
            margins = self.kite.margins()
            
            # Update cache
            self._margins_cache = margins
            self._cache_timestamp = datetime.now()
            
            return margins
            
        except Exception as e:
            logger.error(f"Error fetching margins from Kite: {e}")
            
            # Return stale cache if available
            if self._margins_cache:
                logger.warning("Using stale margins cache due to Kite error")
                return self._margins_cache
            
            return None
    
    def _invalidate_cache(self):
        """Invalidate margins cache"""
        self._margins_cache = None
        self._cache_timestamp = None
        logger.debug("Margins cache invalidated")
    
    # ================================================================
    # BACKGROUND SYNC TO DATABASE
    # ================================================================
    
    async def sync_margins_to_db(self):
        """
        Sync current margins from Kite to database (background job).
        
        Updates capital_state table with latest values from Kite.
        """
        try:
            # Invalidate cache to force fresh fetch
            self._invalidate_cache()
            
            margins = await self._get_kite_margins_cached()
            
            if not margins or 'equity' not in margins:
                logger.warning("No margins data from Kite for sync")
                return
            
            equity = margins['equity']
            available = equity.get('available', {})
            utilised = equity.get('utilised', {})
            
            # Extract values
            cash = available.get('cash', 0.0)
            collateral = available.get('collateral', 0.0)
            available_capital = cash + collateral
            
            net = equity.get('net', 0.0)
            debits = utilised.get('debits', 0.0)
            
            m2m_realised = utilised.get('m2m_realised', 0.0)
            m2m_unrealised = utilised.get('m2m_unrealised', 0.0)
            opening_balance = utilised.get('opening_balance', 0.0)
            
            # Get positions count
            open_positions_count = await self.position_manager.get_open_positions_count()
            
            # Calculate realized P&L (current - opening + unrealized)
            realized_pnl = (net - opening_balance) - m2m_unrealised
            
            # Check if record exists
            existing = await self._get_capital_state()
            
            if existing:
                # Update existing record
                await self.db.update(
                    "capital_state",
                    {
                        "current_capital": net,
                        "available_capital": available_capital,
                        "capital_in_positions": debits,
                        "open_positions_count": open_positions_count,
                        "realized_pnl": realized_pnl,
                        "unrealized_pnl": m2m_unrealised,
                        "total_pnl": m2m_realised + m2m_unrealised
                    },
                    {"date": date.today()}
                )
            else:
                # Insert new record
                await self.db.insert("capital_state", {
                    "date": date.today(),
                    "starting_capital": opening_balance,
                    "current_capital": net,
                    "available_capital": available_capital,
                    "capital_in_positions": debits,
                    "capital_in_pending_orders": 0,
                    "total_risk": 0,
                    "max_risk_allowed": net * (self.limits.max_capital_at_risk_pct / 100),
                    "open_positions_count": open_positions_count,
                    "max_positions_allowed": self.limits.max_positions,
                    "realized_pnl": realized_pnl,
                    "unrealized_pnl": m2m_unrealised,
                    "total_pnl": m2m_realised + m2m_unrealised
                })
            
            logger.info(
                f"Margins synced to DB: Net=₹{net:,.2f}, "
                f"Available=₹{available_capital:,.2f}, "
                f"Used=₹{debits:,.2f}, "
                f"P&L=₹{m2m_realised + m2m_unrealised:,.2f}"
            )
            
        except Exception as e:
            logger.error(f"Error syncing margins to DB: {e}")
    
    # ================================================================
    # DATABASE OPERATIONS (FOR HISTORICAL TRACKING)
    # ================================================================
    
    async def _get_capital_state(self) -> Optional[dict]:
        """Get today's capital state from DB"""
        try:
            result = await self.db.fetch_one(
                "SELECT * FROM capital_state WHERE date = $1",
                {"1": date.today()}
            )
            return result
        except Exception as e:
            logger.error(f"Error fetching capital state: {e}")
            return None
    
    async def initialize_daily_capital(self):
        """
        Initialize capital state for the day from Kite margins.
        
        Called once at market open to sync opening balance.
        """
        try:
            # Check if already initialized
            existing = await self._get_capital_state()
            if existing:
                logger.info("Capital already initialized for today")
                return
            
            # Fetch from Kite
            margins = await self._get_kite_margins_cached()
            
            if margins and 'equity' in margins:
                equity = margins['equity']
                utilised = equity.get('utilised', {})
                opening_balance = utilised.get('opening_balance', self.limits.starting_capital)
            else:
                opening_balance = self.limits.starting_capital
            
            # Insert new record
            await self.db.insert("capital_state", {
                "date": date.today(),
                "starting_capital": opening_balance,
                "current_capital": opening_balance,
                "available_capital": opening_balance,
                "capital_in_positions": 0,
                "capital_in_pending_orders": 0,
                "total_risk": 0,
                "max_risk_allowed": opening_balance * (self.limits.max_capital_at_risk_pct / 100),
                "open_positions_count": 0,
                "max_positions_allowed": self.limits.max_positions,
                "realized_pnl": 0,
                "unrealized_pnl": 0,
                "total_pnl": 0
            })
            
            logger.info(f"Capital initialized from Kite: ₹{opening_balance:,.2f}")
            
        except Exception as e:
            logger.error(f"Error initializing capital: {e}")
    
    # ================================================================
    # REPORTING
    # ================================================================
    
    async def get_capital_summary(self) -> dict:
        """
        Get capital summary from Kite (real-time) and DB (historical).
        
        Returns:
            Comprehensive capital summary
        """
        try:
            # Get real-time from Kite
            margins = await self._get_kite_margins_cached()
            
            if margins and 'equity' in margins:
                equity = margins['equity']
                available = equity.get('available', {})
                utilised = equity.get('utilised', {})
                
                cash = available.get('cash', 0.0)
                collateral = available.get('collateral', 0.0)
                available_capital = cash + collateral
                
                net = equity.get('net', 0.0)
                debits = utilised.get('debits', 0.0)
                
                opening_balance = utilised.get('opening_balance', 0.0)
                m2m_realised = utilised.get('m2m_realised', 0.0)
                m2m_unrealised = utilised.get('m2m_unrealised', 0.0)
                
                # Get positions count
                open_positions = await self.position_manager.get_open_positions_count()
                
                return {
                    "source": "kite",
                    "starting_capital": opening_balance,
                    "current_capital": net,
                    "available_capital": available_capital,
                    "available_cash": cash,
                    "available_collateral": collateral,
                    "capital_in_positions": debits,
                    "total_pnl": m2m_realised + m2m_unrealised,
                    "realized_pnl": m2m_realised,
                    "unrealized_pnl": m2m_unrealised,
                    "open_positions": open_positions,
                    "max_positions": self.limits.max_positions,
                    "timestamp": datetime.now().isoformat()
                }
            
            # Fallback to DB
            logger.warning("Kite unavailable, using DB for summary")
            state = await self._get_capital_state()
            
            if not state:
                return {
                    "source": "default",
                    "starting_capital": self.limits.starting_capital,
                    "current_capital": self.limits.starting_capital,
                    "available_capital": self.limits.starting_capital,
                    "capital_in_positions": 0,
                    "total_pnl": 0,
                    "open_positions": 0,
                    "max_positions": self.limits.max_positions
                }
            
            return {
                "source": "database",
                "starting_capital": state['starting_capital'],
                "current_capital": state['current_capital'],
                "available_capital": state['available_capital'],
                "capital_in_positions": state['capital_in_positions'],
                "total_pnl": state['total_pnl'],
                "realized_pnl": state['realized_pnl'],
                "unrealized_pnl": state['unrealized_pnl'],
                "open_positions": state['open_positions_count'],
                "max_positions": state['max_positions_allowed'],
                "total_risk": state['total_risk'],
                "max_risk_allowed": state['max_risk_allowed'],
                "timestamp": state.get('updated_at', datetime.now()).isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting capital summary: {e}")
            return {}
