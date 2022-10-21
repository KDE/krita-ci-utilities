# Represents a CI build configuration flavor
#
# This primarily consists of the operating system, but can contain a hierarchical set
# of parameters as well.
# A platform flavor is represented as a /-separated string, with the first element
# typically being the operating system, e.g. "Linux/Qt6" or "Windows/Qt5/static".
#
# Platform flavors are matched hierarchically against (partial) platform flavors
# in CI configuration files, ie. a configuration for "Linux" applies to "Linux/Qt5".
#
class PlatformFlavor:
    flavor = []
    os = ''

    def __init__(self, platformStr):
        self.flavor = platformStr.split('/')
        self.os = self.flavor[0]

    def matches(self, flavorSet):
        # catch-all special marker
        if '@all' in flavorSet or '@everything' in flavorSet:
            return True
        # check if one of the given flavors is a prefix of self.flavor
        for flavorStr in flavorSet:
            f = flavorStr.split('/')
            if len(f) > len(self.flavor):
                continue
            if f == self.flavor[0:len(f)]:
                return True
        return False
