MYDIR=$(shell basename `pwd`)

test:
	cd .. && ./testsuite.py $(MYDIR)

debug:
	cd .. && ./testsuite.py $(MYDIR) --debug

coverage:
	rm -rf annotate;
	cd .. && ./testsuite.py $(MYDIR) --coverage
	mv ../annotate .

