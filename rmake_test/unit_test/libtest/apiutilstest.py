from rmake_test import rmakehelp


from rmake.lib import apiutils

class ApiUtilsTest(rmakehelp.RmakeHelper):
    def testRegisterFreezableClassmap(self):
        class Freezable(object):
            def __freeze__(self):
                return {}
            @classmethod
            def __thaw__(class_, d):
                return class_()
            
        class Foo(Freezable):
            pass
        class Bar(Freezable):
            pass

        apiutils.register_freezable_classmap('mytype', Foo)
        apiutils.register_freezable_classmap('mytype', Bar)

        assert(apiutils.thaw('mytype', 
               apiutils.freeze('mytype', Foo())).__class__ == Foo)
        assert(apiutils.thaw('mytype', 
               apiutils.freeze('mytype', Bar())).__class__ == Bar)

