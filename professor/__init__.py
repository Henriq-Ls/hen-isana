"""Integração opcional do modo professor."""

from .professor import Professor, ProfessorRateLimitError
from .professor_llama import ProfessorLlama

__all__ = ["Professor", "ProfessorLlama", "ProfessorRateLimitError"]