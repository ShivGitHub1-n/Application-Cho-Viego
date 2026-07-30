from __future__ import annotations

from typing import Protocol

from resume_tailor.domain.company_research import ApprovedCompanySource, CompanySourceDocument


class CompanySourceFetcher(Protocol):
    def fetch(
        self,
        source: ApprovedCompanySource,
        *,
        company_domain: str,
    ) -> CompanySourceDocument: ...


__all__ = ["CompanySourceFetcher"]
