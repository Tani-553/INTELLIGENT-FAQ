# Intelligent FAQ Answering System using First-Order Logic (FOL)

**Domain:** Hospital information and FAQ system for a fictional "CityCare Hospital".
**Type:** Academic mini-project prototype. It is **not** a medical diagnosis system.

## Objective

Answer general hospital questions (doctors, departments, facilities, services, timings)
using **logical inference**, not hard-coded answers. Every answer is derived by the
pyDatalog engine from facts and rules, and the system shows a **reasoning trace** that
explains how the answer was obtained. It works fully offline and uses no LLM or AI API.

## Features

- Natural-language question -> logical query -> pyDatalog inference -> answer + reasoning trace
- Facts stored in `knowledge_base.json`; rules defined in `inference_engine.py`
- Simple Tkinter GUI (question, answer, reasoning trace)
- Admin / Knowledge Engineer window: add, edit, delete facts, save, reload, validate, timestamped backup, test logical queries
- Validation (empty predicate, wrong number of arguments, duplicate facts, rule-derived predicates)
- Friendly handling of empty questions, unknown questions, broken or missing JSON, and inference errors
- Medical-advice questions are refused with a clear message
- Unknown questions are never guessed: "Sorry, I could not derive an answer..."

## Architecture

```
User question
     |
query_processor.py      -> intent + entities -> logical query, e.g. specializes(Doctor, cardiology)
     |
inference_engine.py     -> pyDatalog evaluates the query against facts + rules
     |
knowledge_base.json     -> facts (loaded through knowledge_base.py)
     |
reasoning_trace.py      -> formats the answer and builds the trace from the facts/rules actually used
     |
gui.py (Tkinter)        -> shows Answer and Reasoning Trace
```

Project files:

```
hospital_faq/
  main.py               start the application
  gui.py                Tkinter user window + admin windows (no inference logic)
  query_processor.py    natural language -> logical query (regular expressions, no AI)
  inference_engine.py   pyDatalog rules, loading facts, running queries
  reasoning_trace.py    answer text + reasoning trace + the full question->answer pipeline
  knowledge_base.py     read/write/validate/backup knowledge_base.json
  knowledge_base.json   the hospital facts
  requirements.txt
  README.md
```

## Technologies

Python 3, Tkinter, pyDatalog, JSON, standard library only. No database, no internet.

## Installation

1. Install Python 3 (3.9 or newer). Tkinter comes with Python on Windows and macOS.
   On Ubuntu/Debian: `sudo apt install python3-tk`
2. Open a terminal in the `hospital_faq` folder and run:

```
pip install -r requirements.txt
```

## How to run

```
python main.py
```

(On some systems use `python3 main.py`.)

## Run the regression tests

```
python -m unittest -v
```

The persistence and administrator tests use temporary knowledge-base files, so
they do not modify `knowledge_base.json`.

## Demo admin credentials

| Username | Password |
|----------|----------|
| admin    | admin123 |

**This is prototype authentication only.** The credentials are written in the source code
and are not secure. A real system would need proper authentication.

## Sample questions

- Which doctor specializes in cardiology? -> *Dr. Arun specializes in Cardiology.*
- Who is the neurologist? -> *Dr. Priya specializes in Neurology.*
- Which doctor works in orthopedics? -> *Dr. Kumar works in Orthopedics.* (uses a rule)
- Does the hospital have an MRI? -> *Yes, CityCare Hospital has an MRI facility.*
- Does the hospital have a blood bank? / a laboratory?
- What facilities are available? / What services does the hospital provide?
- Does the hospital have an ICU? / Does the hospital provide surgery?
- When is Dr. Arun available? / What are the doctor timings?
- What are the hospital timings? -> *Hospital timings are Daily, 8:00 AM - 8:00 PM.*
- What are the OPD timings? -> *OPD timings are 9:00 AM - 5:00 PM.*
- When are visiting hours? -> *Visiting hours are 4:00 PM - 7:00 PM.*
- Is emergency service available? -> *Yes, emergency service is available.*

Extra patterns: pharmacy / lab timings, departments, list of doctors, "What does Dr. Arun specialize in?",
"Does the hospital provide radiology?", "Does the hospital have a cardiology department?".

## Live demonstration (knowledge base controls the answers)

1. Ask: `Which doctors specialize in cardiology?` -> Dr. Arun
2. Click **Admin**, log in, click **Add Fact**: predicate `specializes`, Argument 1 `ravi`, Argument 2 `cardiology`, click **Add**.
3. Ask the same question again -> Dr. Arun and Dr. Ravi. Look at the trace: it now lists `specializes(ravi, cardiology)`.
4. Ask `Which doctor works in cardiology?` -> both doctors again, this time derived by the rule `works_in`.
5. In Admin, select the new fact and click **Delete Fact**; ask again -> only Dr. Arun.

The knowledge base file `knowledge_base.json` really changes each time. The inference engine is reloaded from it.

## First-Order Logic explanation

Knowledge is written as **predicates** applied to **constants**:

```
specializes(arun, cardiology)          a fact: Arun specializes in cardiology
has_facility(citycare_hospital, mri)   a fact: the hospital has an MRI
```

**Rules** derive new facts from existing ones ("<=" means "if"):

```
works_in(D, Dep)         <= specializes(D, Dep)
available_facility(H, F) <= has_facility(H, F) & facility(F)
available_service(H, S)  <= provides(H, S) & service(S)
emergency_ready(H)       <= provides(H, 'emergency') & emergency_available(H, 'true')
doctor_available(D, T)   <= doctor(D) & doctor_availability(D, T)
hospital_open(H, T)      <= hospital_timing(H, T)
```

A **logical query** contains variables (capital letters). `specializes(Doctor, cardiology)` means
"find every Doctor for whom this is true". pyDatalog searches the facts and rules and returns the values
(`Doctor = arun`). `works_in` is never stored as a fact: it exists only through the rule, so these answers
are really *inferred*.

## Reasoning trace explanation

The trace shows (1) the logical query, (2) whether the predicate is derived by a rule, (3) each answer
with the facts that support it, and for rule-derived answers the rule and each condition it needed,
(4) the final conclusion. Supporting facts are checked against the inference engine,
so the trace changes when the knowledge base changes. For failed queries it shows which conditions had
no matching fact, then "No matching fact or rule was found."

## Limitations

- The prototype supports a predefined set of natural-language question patterns.
- The knowledge base is domain-specific (one fictional hospital).
- Facts are currently maintained manually by an administrator.
- A large-scale deployment could automatically populate facts from hospital databases.
- Authentication is only for demonstration.
- A fact that is missing is treated as "cannot derive an answer", not as "no".
- This is not a medical diagnosis or treatment system.

## Future enhancements

- More question patterns and synonyms; spelling-mistake tolerance
- Doctor schedules, appointment slots, room and department locations
- Populate facts automatically from a hospital database
- Real authentication and an audit log of knowledge base changes
- Multi-hospital support and multiple languages
