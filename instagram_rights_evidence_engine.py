import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("InstagramRightsEvidenceEngine")


VALID_RIGHTS_STATUSES: Set[str] = {
    "OWNED",
    "LICENSED",
    "EXPLICITLY_AUTHORIZED",
    "VERIFIED_CC_LICENSE",
    "PERMITTED_COMMERCIAL_REUSE",
    "CC_LICENSE_ALLOWED",
    "USER_PROVIDED_WITH_PERMISSION",
}

AMBIGUOUS_RIGHTS_STATUSES: Set[str] = {
    "RIGHTS_EVIDENCE_MISSING",
    "UNKNOWN",
    "AMBIGUOUS_REUSE",
    "NON_COMMERCIAL_ONLY",
    "REUSE_PROHIBITED",
    "COPYRIGHTED_MATCH_FOOTAGE",
    "FALSE_RIGHTS",
    "UNCERTAIN",
    "UNVERIFIED",
}


@dataclass
class RightsVerificationResult:
    is_valid: bool
    rights_status: str
    rights_evidence: str
    license_url: str
    commercial_use_allowed: bool
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "rights_status": self.rights_status,
            "rights_evidence": self.rights_evidence,
            "license_url": self.license_url,
            "commercial_use_allowed": self.commercial_use_allowed,
            "reasons": self.reasons,
        }


class InstagramRightsEvidenceEngine:
    """Production-safe Item-Level Rights Evidence Engine.

    Verifies explicit reuse rights evidence, excludes ambiguous or missing rights,
    ensures discovery sources are not mistaken for authorization, and enforces
    commercial use permissions.
    """

    def verify_rights_evidence(self, item: Dict[str, Any]) -> RightsVerificationResult:
        reasons = []
        if not item or not isinstance(item, dict):
            return RightsVerificationResult(
                is_valid=False,
                rights_status="RIGHTS_EVIDENCE_MISSING",
                rights_evidence="",
                license_url="",
                commercial_use_allowed=False,
                reasons=["Candidate item payload is empty or invalid."],
            )

        rights_status = (item.get("media_rights_status") or item.get("rights_status") or "RIGHTS_EVIDENCE_MISSING").strip().upper()
        rights_evidence = item.get("rights_evidence") or item.get("rights_evidence_type") or ""
        license_url = item.get("license_url") or item.get("rights_evidence_url") or ""
        
        has_comm_flag = "commercial_use_allowed" in item
        commercial_use_allowed = bool(item.get("commercial_use_allowed", False))

        # 1. Reject ambiguous / missing rights statuses
        if rights_status in AMBIGUOUS_RIGHTS_STATUSES or rights_status not in VALID_RIGHTS_STATUSES:
            reasons.append(f"Rejected ambiguous or unauthorized rights status '{rights_status}'. Discovery alone is not authorization.")

        # 2. Reject missing or false commercial use permission (fail-closed)
        if not has_comm_flag or not commercial_use_allowed:
            reasons.append("Explicit commercial_use_allowed = True permission is required and missing.")

        # 3. Reject copyrighted match footage without explicit license
        is_match_footage = item.get("is_copyrighted_match_footage", False) or "match_footage" in str(item).lower()
        if is_match_footage and rights_status not in ("OWNED", "LICENSED", "EXPLICITLY_AUTHORIZED"):
            reasons.append("Copyrighted match footage requires explicit OWNED or LICENSED authorization.")

        # 4. Require non-empty rights evidence description or license proof
        if not rights_evidence and not license_url:
            reasons.append(f"Media with status '{rights_status}' requires item-level rights evidence or license proof URL.")

        is_valid = len(reasons) == 0
        if not is_valid:
            logger.warning(f"Rights verification REJECTED for '{item.get('content_id', 'unknown')}': {reasons}")

        return RightsVerificationResult(
            is_valid=is_valid,
            rights_status=rights_status,
            rights_evidence=str(rights_evidence),
            license_url=str(license_url),
            commercial_use_allowed=bool(commercial_use_allowed),
            reasons=reasons,
        )
