uv tool install graphifyy      # install the CLI (or: pipx install graphifyy)
graphify install               # register the skill with your AI assistant

cd data/02-wiki
/graphify .

graphify query "LGD downturn"
graphify query "How to calculate the observed LGD?"
graphify query "why IFRS 9 ECL connects provisioning to five other communities, including IRB and SA real estate."
graphify path "LGD" "ECL"
