"""The "brain": everything the agent knows and does, with no audio and no language model.

  diagnosis.py  works out why sales fell, in rupees
  tools.py      what the agent can look up and do (restock plan, price match, ...)
  consent.py    decides whether the seller really said yes
  audit.py      checks the figures the agent spoke against the data
  repo.py       reads and writes the database
  db.py         the database tables
  seed.py       mock sellers
  jobs.py       the nightly scan that flags sellers at risk

Because none of this needs a microphone or an API key, all of it is covered by fast tests.
"""
