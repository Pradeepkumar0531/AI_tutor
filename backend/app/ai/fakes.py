"""Deterministic test-only AI providers. Used by unit tests (injected directly)
and the E2E worker (only when ``TEST_FAKE_AI`` is explicitly enabled).

These are honest stand-ins, not fixtures pretending to be production output:
embeddings are content-derived hashes (stable, correctly-shaped, ordered) and
concepts come from a naive frequency extractor over the actual input text.
Nothing here runs unless a test opts in. NEVER enable in production.
"""

from __future__ import annotations

import hashlib
import logging
import random
import re
from collections import Counter

from app.ai.base import ChatRequest, ChatResponse, EmbedRequest, EmbedResponse
from app.ai.schemas import ConceptExtractionResult, ExtractedConcept

log = logging.getLogger("app.ai.fakes")

_STOPWORDS = frozenset(
    "the a an and or of to in on for with is are was were be been being "
    "this that these those it its as at by from into over after before "
    "such can will would should could may might must shall do does did "
    "not no yes if then than so very just about also there here their "
    "what when where which who whom how why all any each few more most "
    "other some only own same too s t d ll m re ve don isn aren wasn "
    # "chunk" is excluded: _gather_concept_input prefixes blocks with
    # "[chunk N]" markers, which are formatting — not source content.
    "chunk".split()
)


class DeterministicEmbeddingProvider:
    """Content-derived unit vectors: the normalized sum of per-word seeded
    vectors (bag-of-words semantics). Same text always yields the same vector;
    texts sharing words score higher, disjoint texts score near zero — a more
    faithful stand-in for real embedding geometry than whole-text hashes, so
    ordering/threshold/top-k behavior is genuinely testable. Wordless inputs
    fall back to a whole-text hash."""

    name = "fake-embeddings"

    _WORD_RE = re.compile(r"[a-zA-Z]{3,}")

    def __init__(self, *, dimensions: int = 768) -> None:
        log.warning("TEST FAKE AI provider in use (embeddings) — never enable in production")
        self.dimensions = dimensions

    async def embed(self, request: EmbedRequest) -> EmbedResponse:
        vectors = [self._vector_for(text) for text in request.texts]
        return EmbedResponse(embeddings=vectors, model=request.model)

    def _word_vector(self, word: str) -> list[float]:
        seed = int(hashlib.sha256(word.encode("utf-8")).hexdigest(), 16) % (2**32)
        rng = random.Random(seed)
        return [rng.gauss(0.0, 1.0) for _ in range(self.dimensions)]

    def _vector_for(self, text: str) -> list[float]:
        words = self._WORD_RE.findall(text.lower())
        if not words:
            return self._normalize(self._word_vector(f"\x00{text}"))
        vec = [0.0] * self.dimensions
        for word in words:
            for index, value in enumerate(self._word_vector(word)):
                vec[index] += value
        return self._normalize(vec)

    @staticmethod
    def _normalize(vec: list[float]) -> list[float]:
        norm = sum(x * x for x in vec) ** 0.5 or 1.0
        return [x / norm for x in vec]


class NaiveKeywordConceptExtractor:
    """Content-derived concept extraction without any model: top frequent
    content words (with a sentence of context) become concepts. Deterministic
    and grounded by construction."""

    name = "fake-concepts"

    def __init__(self, *, max_concepts: int = 20) -> None:
        log.warning("TEST FAKE AI provider in use (concepts) — never enable in production")
        self.max_concepts = max_concepts

    async def extract(self, source_text: str, *, max_concepts: int) -> ConceptExtractionResult:
        # Strip the "[chunk N]" provenance markers the pipeline prepends: they
        # are formatting, not source content.
        clean = re.sub(r"\[chunk \d+\]\s*", "", source_text)
        words = re.findall(r"[a-zA-Z][a-zA-Z\-]{4,}", clean.lower())
        counts = Counter(w for w in words if w not in _STOPWORDS)
        sentences = re.split(r"(?<=[.!?])\s+", clean.strip())
        concepts: list[ExtractedConcept] = []
        for word, count in counts.most_common(min(max_concepts, self.max_concepts)):
            context = next((s for s in sentences if word in s.lower()), "")
            concepts.append(
                ExtractedConcept(
                    name=word.capitalize(),
                    description=(context[:280] or f"Mentioned {count} times in the material."),
                    importance=min(1.0, 0.3 + 0.1 * count),
                    chunk_refs=[],
                )
            )
        return ConceptExtractionResult(concepts=concepts, relationships=[])


class FakeChatProvider:
    """Deterministic test-only chat provider. Extractive, never generative:
    it answers by quoting leading sentences from the delimited source blocks
    in the user message, so outputs stay grounded in (fake) retrieved content
    by construction. Nothing here runs unless a test opts in."""

    name = "fake-chat"

    def __init__(self) -> None:
        log.warning("TEST FAKE AI provider in use (chat) — never enable in production")

    async def chat(self, request: ChatRequest) -> ChatResponse:
        combined = "\n".join(m.content for m in request.messages if m.role != "system")
        return ChatResponse(content=self._answer(combined), model="fake-chat")

    async def chat_json(
        self, *, system: str, user: str, model: str, max_tokens: int | None = None
    ) -> dict:
        from app.ai.schemas import TutorStructuredOutput

        if "QUIZ QUESTION GENERATOR" in system:
            return self._fake_questions(user)
        if "QUIZ EVALUATOR" in system:
            return self._fake_evaluation(user)
        answer, grounded = self._answer_with_grounding(user)
        return TutorStructuredOutput(
            answer=answer, grounded=grounded, needs_clarification=False
        ).model_dump()

    # ------------------------------------------------ quiz test double
    # Deterministic, extractive, never generative. MCQ correct answers are
    # ALWAYS the first option ("A") by test-double contract, so E2E can answer
    # deterministically; backend tests use custom providers for other layouts.

    def _quiz_sentences(self, user_text: str) -> list[str]:
        from app.ai.prompts import SOURCE_BEGIN, SOURCE_END

        sentences: list[str] = []
        cursor = 0
        while (start := user_text.find(SOURCE_BEGIN, cursor)) != -1:
            end = user_text.find(SOURCE_END, start)
            block = user_text[start + len(SOURCE_BEGIN) : end if end != -1 else len(user_text)]
            block = re.sub(r"(?m)^\[Source \d+\][^\n]*\n?", "", block)
            for sentence in re.split(r"(?<=[.!?])\s+", block):
                sentence = sentence.strip()
                if len(sentence) >= 20:
                    sentences.append(sentence)
                if len(sentences) >= 8:
                    break
            cursor = end + 1 if end != -1 else len(user_text)
        return sentences

    def _fake_questions(self, user_text: str) -> dict:
        import re as _re

        concepts = _re.findall(r"(?m)^CONCEPT: (.+)$", user_text)
        concepts = [c.strip()[:200] for c in concepts if c.strip()]
        count_match = _re.search(r"Generate exactly (\d+) (MCQ|OPEN_ENDED)", user_text)
        count = min(max(int(count_match.group(1)) if count_match else 1, 1), 20)
        qtype = count_match.group(2) if count_match else "MCQ"
        diff_match = _re.search(r"at (EASY|MEDIUM|HARD) difficulty", user_text)
        difficulty = diff_match.group(1) if diff_match else "MEDIUM"
        sentences = self._quiz_sentences(user_text)
        if not concepts:
            concepts = ["the material"]
        if not sentences:
            sentences = ["The material covers this topic in the provided readings."]

        questions: list[dict] = []
        used_prompts: set[str] = set()
        index = 0
        while len(questions) < count:
            concept = concepts[index % len(concepts)]
            if qtype == "OPEN_ENDED":
                prompt = f"Explain {concept} in your own words."
                if prompt in used_prompts:
                    prompt = f"Explain {concept} in your own words (part {index + 1})."
                used_prompts.add(prompt)
                questions.append(
                    {
                        "type": "OPEN_ENDED",
                        "prompt": prompt,
                        "options": [],
                        "correct_option_id": "",
                        "explanation": "",
                        "expected_concepts": [concept],
                        "reference_answer": sentences[index % len(sentences)],
                        "concept_names": [concept],
                        "difficulty": difficulty,
                    }
                )
            else:
                prompt = f"What does the material state about {concept}?"
                if prompt in used_prompts:
                    prompt = f"According to the material, which is true about {concept}?"
                if prompt in used_prompts:
                    prompt = f"What does the material state about {concept}? (part {index + 1})"
                used_prompts.add(prompt)
                correct = sentences[index % len(sentences)]
                distractors = [s for s in sentences if s != correct]
                pad = 1
                while len(distractors) < 3:
                    distractors.append(f"The material does not cover this aspect ({pad}).")
                    pad += 1
                options = [{"id": "A", "text": correct}]
                for option_id, text in zip(("B", "C", "D"), distractors[:3], strict=True):
                    options.append({"id": option_id, "text": text})
                questions.append(
                    {
                        "type": "MCQ",
                        "prompt": prompt,
                        "options": options,
                        "correct_option_id": "A",
                        "explanation": f"This is stated in the material on {concept}.",
                        "expected_concepts": [],
                        "reference_answer": "",
                        "concept_names": [concept],
                        "difficulty": difficulty,
                    }
                )
            index += 1
            if index > count + len(concepts) + 4:  # never spin forever
                break
        return {"questions": questions[:count]}

    def _fake_evaluation(self, user_text: str) -> dict:
        import re as _re

        from app.ai.prompts import SOURCE_BEGIN, SOURCE_END

        blocks: list[str] = []
        cursor = 0
        while (start := user_text.find(SOURCE_BEGIN, cursor)) != -1:
            end = user_text.find(SOURCE_END, start)
            blocks.append(
                user_text[start + len(SOURCE_BEGIN) : end if end != -1 else len(user_text)]
            )
            cursor = end + 1 if end != -1 else len(user_text)
        learner_answer = blocks[-1].strip() if blocks else ""
        ref_match = _re.search(
            r"EXPECTED ANSWER\n(.*?)\n\nREFERENCE MATERIAL", user_text, _re.DOTALL
        )
        reference = ref_match.group(1).strip() if ref_match else ""
        concepts_section = user_text.split("EXPECTED CONCEPTS")[-1].split("EXPECTED ANSWER")[0]
        expected = _re.findall(r"(?m)^- (.+)$", concepts_section)

        def words(text: str) -> set[str]:
            return set(_re.findall(r"[a-zA-Z]{3,}", text.lower()))

        ref_words = words(reference) or words(blocks[0] if blocks else "")
        learner_words = words(learner_answer)
        overlap = len(ref_words & learner_words) / max(len(ref_words), 1)
        correctness = round(min(max(overlap, 0.0), 1.0), 2)
        if correctness >= 0.8:
            understanding, accuracy = "FULL", "CORRECT"
        elif correctness >= 0.5:
            understanding, accuracy = "MOSTLY", "MOSTLY_CORRECT"
        elif correctness >= 0.25:
            understanding, accuracy = "PARTIAL", "PARTIALLY_CORRECT"
        else:
            understanding, accuracy = "NONE", "INCORRECT"
        understood = [
            name for name in expected if name.strip() and words(name.strip()) <= learner_words
        ]
        missing = [name for name in expected if name not in understood]
        if understood:
            feedback = f"You correctly covered: {', '.join(understood)}. " + (
                f"Also review: {', '.join(missing)}."
                if missing
                else "Nothing essential is missing."
            )
        else:
            feedback = "Your answer does not yet cover the expected concepts. " + (
                f"Review: {', '.join(missing)}."
                if missing
                else "Compare your answer with the reference material."
            )
        return {
            "correctness": correctness,
            "understanding": understanding,
            "accuracy": accuracy,
            "relevance": "RELEVANT" if learner_words else "IRRELEVANT",
            "concepts_understood": understood,
            "concepts_missing": missing,
            "feedback": feedback,
        }

    def _answer(self, user_text: str) -> str:
        answer, _ = self._answer_with_grounding(user_text)
        return answer

    def _answer_with_grounding(self, user_text: str) -> tuple[str, bool]:
        """Quote up to two leading sentences found inside source blocks."""
        from app.ai.prompts import SOURCE_BEGIN, SOURCE_END

        sentences: list[str] = []
        cursor = 0
        while (start := user_text.find(SOURCE_BEGIN, cursor)) != -1:
            end = user_text.find(SOURCE_END, start)
            block = user_text[start + len(SOURCE_BEGIN) : end if end != -1 else len(user_text)]
            # Drop per-source header lines ("[Source N] ... — Page X ...").
            block = re.sub(r"(?m)^\[Source \d+\][^\n]*\n?", "", block)
            for sentence in re.split(r"(?<=[.!?])\s+", block):
                sentence = sentence.strip()
                if sentence.startswith("("):
                    continue  # scaffolding placeholders, not source content
                if len(sentence) >= 20:
                    sentences.append(sentence)
                if len(sentences) == 2:
                    break
            cursor = end + 1 if end != -1 else len(user_text)
        if not sentences:
            # No source sentences (e.g. general-mode call with empty evidence):
            # clearly-marked test-double prose, never presented as grounded.
            return (
                "General teaching response (deterministic test double).",
                False,
            )
        return ("Based on your materials: " + " ".join(sentences[:2]), True)
