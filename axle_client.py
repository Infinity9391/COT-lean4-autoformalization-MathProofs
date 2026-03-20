"""
AXLE API client for verifying Lean 4 proofs.

Uses the official axiom-axle SDK (https://axle.axiommath.ai) to type-check
Lean 4 proofs. Falls back to local `lean` if the SDK is unavailable.
"""

import asyncio
import logging
import os
import subprocess
import tempfile

logger = logging.getLogger(__name__)

AXLE_API_KEY_ENV = "AXLE_API_KEY"

# Try importing the official SDK
try:
    from axle import AxleClient as _SdkClient
    _HAS_SDK = True
except ImportError:
    _SdkClient = None
    _HAS_SDK = False


class AxleClient:
    """Wrapper around the axiom-axle SDK with fallback to local Lean."""

    def __init__(
        self,
        api_key: str | None = None,
        environment: str = "lean-4.28.0",
        timeout: float = 120.0,
    ):
        self.api_key = api_key or os.environ.get(AXLE_API_KEY_ENV)
        self.environment = environment
        self.timeout = timeout

        if not _HAS_SDK:
            logger.warning(
                "axiom-axle SDK not installed. Install with: pip install axiom-axle"
            )

    def verify_proof(self, lean_code: str) -> dict:
        """Verify a Lean 4 proof.

        Tries AXLE SDK first, then local lean, then raw output fallback.

        Returns:
            Dict with keys:
                - verified: bool | None — whether the proof type-checks
                - method: str — "axle_api", "lean_local", or "raw_output"
                - details: str — error message or success info
                - errors: list[str] — individual error messages
                - raw_response: dict | None — full response if available
        """
        result = self._try_axle_sdk(lean_code)
        if result is not None:
            return result

        result = self._try_lean_local(lean_code)
        if result is not None:
            return result

        logger.warning("No verification method available; logging raw output.")
        return {
            "verified": None,
            "method": "raw_output",
            "details": "No verification backend available. Raw code logged.",
            "errors": [],
            "raw_response": None,
        }

    def _try_axle_sdk(self, lean_code: str) -> dict | None:
        """Verify using the official axiom-axle SDK."""
        if not _HAS_SDK:
            return None
        try:
            return asyncio.run(self._axle_verify_async(lean_code))
        except Exception as e:
            logger.warning("AXLE SDK error: %s", e)
            return None

    async def _axle_verify_async(self, lean_code: str) -> dict:
        """Async AXLE verification call using client.check()."""
        kwargs = {}
        if self.api_key:
            kwargs["api_key"] = self.api_key

        async with _SdkClient(**kwargs) as client:
            result = await client.check(
                content=lean_code,
                environment=self.environment,
            )

        errors = []
        if hasattr(result, "lean_messages") and result.lean_messages:
            for attr in ("errors", "warnings"):
                msgs = getattr(result.lean_messages, attr, [])
                if msgs:
                    errors.extend(str(m) for m in msgs)
        if hasattr(result, "tool_messages") and result.tool_messages:
            for attr in ("errors", "warnings"):
                msgs = getattr(result.tool_messages, attr, [])
                if msgs:
                    errors.extend(str(m) for m in msgs)

        verified = bool(result.okay) if hasattr(result, "okay") else None

        return {
            "verified": verified,
            "method": "axle_api",
            "details": "; ".join(errors[:5]) if errors else ("Verified." if verified else "Check failed."),
            "errors": errors,
            "raw_response": str(result),
        }

    def _try_lean_local(self, lean_code: str) -> dict | None:
        """Attempt to verify using local Lean 4 installation."""
        lean_bin = None
        for path in ["lean", "/tmp/lean4/lean-4.14.0-linux/bin/lean"]:
            try:
                subprocess.run(
                    [path, "--version"],
                    capture_output=True,
                    check=True,
                    timeout=10,
                )
                lean_bin = path
                break
            except (FileNotFoundError, subprocess.CalledProcessError, OSError):
                continue

        if lean_bin is None:
            logger.info("Local Lean 4 not available.")
            return None

        with tempfile.NamedTemporaryFile(suffix=".lean", mode="w", delete=False) as f:
            f.write(lean_code)
            tmpfile = f.name

        try:
            result = subprocess.run(
                [lean_bin, tmpfile],
                capture_output=True,
                text=True,
                timeout=120,
            )
            verified = result.returncode == 0
            error_output = (result.stdout + "\n" + result.stderr).strip()
            details = "Type-check passed." if verified else error_output[:500]
            return {
                "verified": verified,
                "method": "lean_local",
                "details": details,
                "errors": [details] if not verified else [],
                "raw_response": {
                    "returncode": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                },
            }
        except subprocess.TimeoutExpired:
            return {
                "verified": False,
                "method": "lean_local",
                "details": "Lean type-check timed out after 120s.",
                "errors": ["timeout"],
                "raw_response": None,
            }
        finally:
            os.unlink(tmpfile)


def verify_proof(lean_code: str, **kwargs) -> dict:
    """Convenience function to verify a single proof."""
    client = AxleClient(**kwargs)
    return client.verify_proof(lean_code)
