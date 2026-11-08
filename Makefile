.PHONY: test poc
test:
	python3 -m unittest discover -s tests -v
poc:
	python3 -m testbed.runner --output results
