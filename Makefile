.PHONY: build up status grade reset verify down repair after-action
build up status grade reset verify down repair after-action:
	python3 testbed/runner.py $@
