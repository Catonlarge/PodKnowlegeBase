"""
Proofreading Service Business Validator

This module provides business logic validation for proofreading service.
It validates Pydantic-validated responses against business rules.
"""
from typing import Set
from loguru import logger

from app.services.ai.schemas.proofreading_schema import ProofreadingResponse


class ProofreadingValidator:
    """
    Business logic validator for proofreading service.

    Validates:
    - All cue_ids are within valid range
    - Correction count doesn't exceed total cues
    - Low confidence warnings
    """

    @staticmethod
    def validate(
        response: ProofreadingResponse,
        valid_cue_ids: Set[int],
        total_cues: int
    ) -> ProofreadingResponse:
        """
        Validate proofreading response against business rules.

        Args:
            response: Validated Pydantic response
            valid_cue_ids: Set of valid cue IDs from database
            total_cues: Total number of cues in the batch

        Returns:
            The validated response (unchanged if validation passes)

        Raises:
            ValueError: If business validation fails

        Examples:
            >>> validator = ProofreadingValidator()
            >>> result = validator.validate(response, valid_cue_ids={1,2,3}, total_cues=10)
        """
        # Validation 1: All cue_ids are within valid range
        response_cue_ids = {c.cue_id for c in response.corrections}
        invalid_ids = response_cue_ids - valid_cue_ids

        if invalid_ids:
            if valid_cue_ids:
                min_id, max_id = min(valid_cue_ids), max(valid_cue_ids)
                raise ValueError(
                    f"发现无效的cue_id: {invalid_ids}. "
                    f"有效范围: {min_id}-{max_id}"
                )
            else:
                raise ValueError(f"发现无效的cue_id: {invalid_ids}. 没有有效的cue_id")

        # Validation 2: Correction count doesn't exceed total cues
        if len(response.corrections) > total_cues:
            raise ValueError(
                f"修正数量({len(response.corrections)}) 超过总条数({total_cues})"
            )

        # Validation 3: Low confidence warnings (don't raise exception)
        for correction in response.corrections:
            if correction.confidence < 0.7:
                logger.warning(
                    f"cue_id {correction.cue_id} 的置信度过低: {correction.confidence:.2f}"
                )

        return response


__all__ = [
    "ProofreadingValidator",
]
