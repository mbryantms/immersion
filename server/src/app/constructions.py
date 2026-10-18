"""Versioned offline contrast practice. Candidate library matches are not parses."""

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Choice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=500)
    explanation: str = Field(min_length=1, max_length=1000)


class MeaningQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: str = Field(min_length=1, max_length=80)
    prompt: str = Field(min_length=1, max_length=1000)
    passage: str = Field(min_length=1, max_length=2000)
    choices: list[Choice] = Field(min_length=2, max_length=4)
    answer: int = Field(ge=0)

    @model_validator(mode="after")
    def valid_key(self):
        if (
            not self.prompt.strip()
            or not self.passage.strip()
            or not self.category.strip()
        ):
            raise ValueError("Question fields cannot be blank")
        if any(
            not choice.text.strip() or not choice.explanation.strip()
            for choice in self.choices
        ):
            raise ValueError("Choices and explanations cannot be blank")
        if self.answer >= len(self.choices):
            raise ValueError("Answer must identify one of the choices")
        if len({choice.text.strip().casefold() for choice in self.choices}) != len(
            self.choices
        ):
            raise ValueError("Choices must be distinct")
        return self


VERSION = "2026-10-18-v1"
# Every option explains its interpretation. These exercise narrow contrasts,
# not unrestricted rules for interpreting arbitrary source sentences.
_DATA = [
    (
        "ba-bei",
        "把 / 被: roles",
        [["把"], ["被"]],
        "把 often brings a definite affected object before the verb; 被 introduces a passive. Identify who acts and who is affected rather than translating Chinese word order mechanically.",
        "小王把书给了小李。",
        "Xiaowang gave the book to Xiaoli.",
        "书被小李拿走了。",
        "The book was taken away by Xiaoli.",
        "agent_patient",
        "In 小王把书给了小李。, who received the book?",
        [
            ("Xiaoli", "给 introduces the recipient 小李 here; 小王 is the giver."),
            ("Xiaowang", "小王 performs the giving; this reverses the roles."),
        ],
        0,
    ),
    (
        "negation",
        "不 / 没: negation",
        [["不"], ["没", "沒"]],
        "不 commonly negates habits, intentions and general states. 没 negates occurrence or possession; 没 + verb + 过 denies a prior experience. Time and verb type matter.",
        "他不喝咖啡。",
        "He does not drink coffee.",
        "他没喝咖啡。",
        "He did not drink coffee.",
        "negation",
        "他没去过北京。 Which meaning is supported?",
        [
            (
                "He has never been to Beijing.",
                "没…过 denies a prior experience of going to Beijing.",
            ),
            (
                "He has been to Beijing.",
                "This drops the negation 没 and reverses the meaning.",
            ),
        ],
        0,
    ),
    (
        "le",
        "了: event and change",
        [["了"]],
        "Verbal 了 can present an event as bounded; sentence-final 了 often signals a changed situation. Neither is simply an English past-tense marker. Context can support other readings.",
        "我吃了饭。",
        "I ate / have eaten a meal.",
        "我会开车了。",
        "I can drive now.",
        "aspect",
        "我会开车了。 What change does the sentence highlight?",
        [
            (
                "I can drive now.",
                "会开车 states an ability; final 了 presents the new situation.",
            ),
            (
                "I no longer know how to drive.",
                "The sentence contains no negation; this reverses the change.",
            ),
        ],
        0,
    ),
    (
        "guo",
        "过: prior experience",
        [["过", "過"]],
        "Experiential 过 presents an experience before the reference time. It does not say that the activity is happening now. Other uses of 过, such as crossing, need different analysis.",
        "我去过上海。",
        "I have been to Shanghai.",
        "我正在去上海。",
        "I am on my way to Shanghai.",
        "aspect",
        "我去过上海。 Does this require the speaker to be in Shanghai now?",
        [
            (
                "No; it reports a prior experience.",
                "Experiential 过 alone does not locate the speaker there now.",
            ),
            (
                "Yes; the trip must be happening now.",
                "Ongoing action would need different contextual evidence, such as 正在.",
            ),
        ],
        0,
    ),
    (
        "zhe",
        "着: maintained state",
        [["着", "著"]],
        "着 often presents a maintained state or continuing manner. Distinguish 门开着 (the door is open) from 打开了门 (an opening event). Not every written 著 is this particle.",
        "门开着。",
        "The door is open.",
        "他打开了门。",
        "He opened the door.",
        "aspect",
        "门开着。 What is foregrounded?",
        [
            (
                "The door's open state.",
                "开着 describes the maintained state in this sentence.",
            ),
            (
                "The door's closed state.",
                "That would require 关着; it is the opposite state.",
            ),
        ],
        0,
    ),
    (
        "result",
        "Result complements",
        [["完"], ["懂"], ["到"]],
        "A result complement describes the outcome of an action: 看懂 means read/watch and understand; 看完 means finish reading/watching. Completing an activity does not guarantee understanding it.",
        "我看完了。",
        "I finished reading/watching it.",
        "我看懂了。",
        "I understood it by reading/watching.",
        "result",
        "我看完了，但是没看懂。 Which interpretation fits?",
        [
            (
                "I finished it but did not understand it.",
                "完 supplies completion; 没…懂 denies the understanding result.",
            ),
            (
                "I understood it but did not finish it.",
                "This swaps the outcomes and puts negation on the wrong complement.",
            ),
        ],
        0,
    ),
    (
        "comparison",
        "比 / 没有: comparison",
        [["比"], ["没有", "沒有"]],
        "A 比 B + adjective compares A against B. A 没有 B + adjective says A does not reach B's degree. Avoid treating either order as interchangeable.",
        "今天比昨天冷。",
        "Today is colder than yesterday.",
        "今天没有昨天冷。",
        "Today is not as cold as yesterday.",
        "comparison",
        "今天比昨天冷。 Which day is colder?",
        [
            (
                "Today",
                "今天 is the item being described as colder than the 昨天 benchmark.",
            ),
            ("Yesterday", "That reverses A and B in the 比 comparison."),
        ],
        0,
    ),
    (
        "concession",
        "虽然…但是 / 还是",
        [["虽然", "雖然"]],
        "虽然 introduces a concession. 但是 or 还是 can introduce a result that holds despite it. The clauses do not necessarily express cause and effect.",
        "虽然下雨，他还是来了。",
        "Although it rained, he still came.",
        "因为下雨，他没来。",
        "Because it rained, he did not come.",
        "paraphrase",
        "虽然下雨，他还是来了。 Which paraphrase preserves the meaning?",
        [
            (
                "He came despite the rain.",
                "The arrival still happened, contrary to the expectation raised by the rain.",
            ),
            (
                "The rain prevented him from coming.",
                "This reverses the stated result 来了.",
            ),
        ],
        0,
    ),
    (
        "de",
        "的 / 地 / 得",
        [["的"], ["地"], ["得"]],
        "的 commonly links an attributive modifier to a noun; 地 links an adverbial modifier to an action; 得 introduces a complement describing degree or manner. Speech, omission and lexicalized forms complicate this spelling guide.",
        "他认真地写字。",
        "He writes carefully.",
        "他写得很认真。",
        "He writes very carefully.",
        "paraphrase",
        "他写得很认真。 What is described as careful?",
        [
            ("His manner of writing.", "得 introduces a description of how he writes."),
            (
                "His handwriting is necessarily beautiful.",
                "Careful effort does not establish that the result is beautiful.",
            ),
        ],
        0,
    ),
    (
        "measure",
        "Measure words",
        [["本"], ["张", "張"], ["个", "個"]],
        "Numeral + measure word + noun counts an item using an appropriate classifier: 一本书, 两张票. Classifier choice depends on the noun and intended unit; 个 is not a universal substitute.",
        "我买了两本书。",
        "I bought two books.",
        "我买了两张票。",
        "I bought two tickets.",
        "meaning",
        "我买了两本书。 What did the speaker buy?",
        [
            ("Two books", "两 supplies two; 本 is the classifier for 书 here."),
            ("Two tickets", "Tickets would normally use 张票, not 本书."),
        ],
        0,
    ),
    (
        "topic",
        "Topic and comment",
        [["这本书", "這本書"]],
        "A phrase can establish what a sentence is about before the comment: 这本书，我看过. The topic is not automatically the agent of the action.",
        "这本书，我看过。",
        "As for this book, I have read it.",
        "这本书，他没看过。",
        "As for this book, he has not read it.",
        "agent_patient",
        "这本书，我看过。 Who has read the book?",
        [
            (
                "The speaker",
                "我 is the person who performed 看; 这本书 is the topic and object.",
            ),
            (
                "The book",
                "The topic is not the agent; the book does not perform the reading.",
            ),
        ],
        0,
    ),
    (
        "separable",
        "Separable verb–object forms",
        [["见", "見"], ["洗"]],
        "Some familiar words contain a verb and object that can separate: 见面 → 见了面, 洗澡 → 洗了个澡. Separability is lexical; do not split arbitrary two-character verbs.",
        "我们见了面。",
        "We met.",
        "他洗了个澡。",
        "He took a shower.",
        "paraphrase",
        "我们昨天见了面。 Which paraphrase fits?",
        [
            (
                "We met yesterday.",
                "见了面 is an expanded form of 见面; 昨天 supplies yesterday.",
            ),
            (
                "We will meet tomorrow.",
                "That changes both the stated time and the event's presentation.",
            ),
        ],
        0,
    ),
]

CONSTRUCTIONS = {}
for key, title, markers, note, a, ae, b, be, category, prompt, options, answer in _DATA:
    question = MeaningQuestion(
        category=category,
        prompt=prompt,
        passage=a
        if key not in ("negation", "result", "separable")
        else {
            "negation": "他没去过北京。",
            "result": "我看完了，但是没看懂。",
            "separable": "我们昨天见了面。",
        }[key],
        choices=[
            Choice(text=text, explanation=explanation) for text, explanation in options
        ],
        answer=answer,
    )
    import hashlib

    offset = hashlib.sha256(key.encode()).digest()[0] % len(question.choices)
    question.choices = question.choices[offset:] + question.choices[:offset]
    question.answer = (question.answer - offset) % len(question.choices)
    CONSTRUCTIONS[key] = {
        "id": key,
        "title": title,
        "markers": markers,
        "note": note,
        "examples": [{"zh": a, "en": ae}, {"zh": b, "en": be}],
        "question": question,
    }
