# Changes

The changes made by AlainLich are documented here, in case a PR gets
accepted, they may have to be integrated in the main documentation


## Command line additions

1. Added flag --listFns to list available functions as a help for using 
   the -z  and -l flags. The argument value is a selector which is used
   for Unix pattern matching as with -l or -z flags; thereby helping the
   user select a subgraph.
    ~~~
    prof2dot.py -f pstats /tmp/myLog.profile  --listFns "test_segments:*:*" 
    
    test_segments:5:<module>,
    test_segments:206:TestSegments,
    test_segments:46:<lambda>
    ~~~

  + Documentation: 
    - flag `--listFns`: list functions available for selection in -z or -l, 
	  requires selector argument  ( use '+' to select all).
	   
    - Recall that the selector argument is used with Unix/Bash globbing/pattern matching,
      and that entries are formatted '\<pkg\>:\<linenum\>:\<function\>'. When argument 
	  starts with '%', a dump of all available information is performed for 
	  selected entries,   after removal of selector's leading '%'.
