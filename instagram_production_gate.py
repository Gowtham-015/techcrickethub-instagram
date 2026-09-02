import logging
from dataclasses import dataclass, field
from typing import List, Optional
from config import Config
from instagram_health import InstagramHealthTracker

logger = logging.getLogger("InstagramProductionGate")


@dataclass
class GateEvaluationResult:
    can_publish: bool
    status: str  # LOCKED, DRY_RUN, NOT_CONFIGURED, READY, LIVE_TEST, PRODUCTION, BLOCKED
    reasons: List[str] = field(default_factory=list)
    dry_run: bool = True
    production_enabled: bool = False
    live_test_enabled: bool = False
    paused: bool = False


class InstagramProductionGate:
    """Production Safety Gate ensuring controlled Instagram live publishing."""

    def __init__(self, config: Optional[Config] = None, health_tracker: Optional[InstagramHealthTracker] = None):
        self.config = config
        self.health_tracker = health_tracker

    def evaluate(
        self,
        config: Optional[Config] = None,
        health_tracker: Optional[InstagramHealthTracker] = None,
        is_live_test: bool = False,
    ) -> GateEvaluationResult:
        """Evaluates whether live publishing can proceed based on strict safety rules."""
        cfg = config or self.config
        health = health_tracker or self.health_tracker

        if cfg is None:
            return GateEvaluationResult(
                can_publish=False,
                status="NOT_CONFIGURED",
                reasons=["Configuration is missing or None."],
            )

        reasons = []

        # 1. Credential check
        has_user_id = bool(cfg.user_id and cfg.user_id.strip())
        has_token = bool(
            cfg.access_token
            and cfg.access_token.strip()
            and cfg.access_token != "YOUR_ACCESS_TOKEN_HERE"
        )

        if not has_user_id or not has_token:
            if not has_user_id:
                reasons.append("INSTAGRAM_USER_ID is missing.")
            if not has_token:
                reasons.append("INSTAGRAM_ACCESS_TOKEN is missing or set to placeholder.")
            return GateEvaluationResult(
                can_publish=False,
                status="NOT_CONFIGURED",
                reasons=reasons,
                dry_run=cfg.dry_run,
                production_enabled=cfg.production_enabled,
                live_test_enabled=cfg.live_test_enabled,
            )

        # 2. Safety pause check from health tracker
        if health is not None:
            health_data = health.get_health_summary()
            if health_data.get("production_paused", False):
                reason = health_data.get("pause_reason", "CONSECUTIVE_PUBLISH_FAILURES")
                reasons.append(f"Production publishing is PAUSED due to: {reason}")
                return GateEvaluationResult(
                    can_publish=False,
                    status="BLOCKED",
                    reasons=reasons,
                    dry_run=cfg.dry_run,
                    production_enabled=cfg.production_enabled,
                    live_test_enabled=cfg.live_test_enabled,
                    paused=True,
                )

        # 3. Dry-run mode check
        if cfg.dry_run:
            reasons.append("INSTAGRAM_DRY_RUN is enabled (true). Real publishing is blocked.")
            return GateEvaluationResult(
                can_publish=False,
                status="DRY_RUN",
                reasons=reasons,
                dry_run=True,
                production_enabled=cfg.production_enabled,
                live_test_enabled=cfg.live_test_enabled,
            )

        # 4. Live Test Mode check
        if is_live_test or cfg.live_test_enabled:
            return GateEvaluationResult(
                can_publish=True,
                status="LIVE_TEST",
                reasons=["Live Test Mode active. Exactly one post allowed."],
                dry_run=False,
                production_enabled=cfg.production_enabled,
                live_test_enabled=True,
            )

        # 5. Production enabled check
        if not cfg.production_enabled:
            reasons.append("INSTAGRAM_PRODUCTION_ENABLED is set to false. Live publishing disabled.")
            return GateEvaluationResult(
                can_publish=False,
                status="BLOCKED",
                reasons=reasons,
                dry_run=False,
                production_enabled=False,
                live_test_enabled=cfg.live_test_enabled,
            )

        # 6. Production Ready
        return GateEvaluationResult(
            can_publish=True,
            status="READY",
            reasons=["All production safety checks passed."],
            dry_run=False,
            production_enabled=True,
            live_test_enabled=False,
        )

    def validate_credentials_safe(self, config: Optional[Config] = None) -> dict:
        """Returns safe credential status report without exposing secret tokens."""
        cfg = config or self.config
        if not cfg:
            return {
                "user_id": "NOT_CONFIGURED",
                "access_token": "NOT_CONFIGURED",
                "api_version": "v26.0",
                "credential_exposure": "NONE",
            }

        user_status = "CONFIGURED" if (cfg.user_id and cfg.user_id.strip()) else "NOT_CONFIGURED"
        token_status = (
            "CONFIGURED"
            if (cfg.access_token and cfg.access_token.strip() and cfg.access_token != "YOUR_ACCESS_TOKEN_HERE")
            else "NOT_CONFIGURED"
        )

        return {
            "user_id": user_status,
            "access_token": token_status,
            "api_version": cfg.api_version,
            "credential_exposure": "NONE",
        }
