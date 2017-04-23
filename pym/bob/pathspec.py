
from collections import namedtuple
from fnmatch import fnmatchcase
import pyparsing

# nodes of name graph
GraphNode = namedtuple('GraphNode', ['parents', 'childs'])

class PathAction:
    def __init__(self, toks, graph):
        self.__path = [
            (StepAction(['descendant-or-self', '@', '*'], graph) if t == "//" else t)
            for t in toks
            if t != "/"
        ]
        self.__graph = graph

    def __repr__(self):
        return "PathAction({})".format(self.__path)

    def evalForward(self, root):
        nodes = set([root])
        valid = set([root])
        for i in self.__path:
            oldNodes = nodes
            nodes = i.evalForward(nodes, valid)
            valid.update(self.__findIntermediateNodes(oldNodes, nodes))
            valid.update(nodes)
        return (nodes, valid)

    def __findIntermediateNodes(self, old, new):
        visited = set()
        intermediate = set()
        if old.issuperset(new): return intermediate

        #print(old)
        #print(new)

        def traverse(node, stack):
            if node in visited: return

            if node in new:
                intermediate.update(stack)
            else:
                stack = stack + [node]
                for i in self.__graph[node].childs:
                    traverse(i, stack)
                visited.add(node)

        for n in old: traverse(n, [])

        #print(intermediate)
        #print("====================")
        return intermediate

class StepAction:
    def __init__(self, step, graph):
        self.__graph = graph
        self.__pred = None
        if len(step) == 1:
            if step[0] == '.':
                self.__axis = 'self'
                self.__test = '*'
            elif step[0] == '..':
                self.__axis = 'parent'
                self.__test = '*'
            else:
                self.__axis = 'child'
                self.__test = step[0]
        else:
            if step[1] == '@':
                self.__axis = step[0]
                self.__test = step[2]
                remain = step[3:]
            else:
                self.__axis = 'child'
                self.__test = step[0]
                remain = step[1:]

            if remain:
                assert remain[0] == '['
                assert remain[2] == ']'
                self.__pred = remain[1]

    def __repr__(self):
        return "StepAction({}@{}[{}])".format(self.__axis, self.__test, self.__pred)

    def __evalAxisChild(self, nodes):
        ret = set()
        for i in nodes:
            ret.update(self.__graph[i].childs)
        return ret

    def __evalAxisDescendant(self, nodes):
        ret = set()
        todo = nodes
        while todo:
            childs = set()
            for i in todo: childs.update(self.__graph[i].childs)
            todo = childs - ret
            ret.update(childs)
        return ret

    def __evalAxisParent(self, nodes):
        ret = set()
        for i in nodes:
            ret.update(self.__graph[i].parents)
        return ret

    def __evalAxisAncestor(self, nodes):
        ret = set()
        todo = nodes
        while todo:
            parents = set()
            for i in todo: parents.update(self.__graph[i].parents)
            todo = parents - ret
            ret.update(parents)
        return ret

    def evalForward(self, nodes, valid):
        #print(">> evalForward", self.__axis, self.__test, len(nodes))

        oldNodes = nodes
        if self.__axis == "child":
            nodes = self.__evalAxisChild(nodes)
        elif self.__axis == "descendant":
            nodes = self.__evalAxisDescendant(nodes)
        elif self.__axis == "parent":
            nodes = self.__evalAxisParent(nodes) & valid
        elif self.__axis == "ancestor":
            nodes = self.__evalAxisAncestor(nodes) & valid
        elif self.__axis == "self":
            pass
        elif self.__axis == "descendant-or-self":
            nodes = self.__evalAxisDescendant(nodes) | nodes
        elif self.__axis == "ancestor-or-self":
            nodes = self.__evalAxisAncestor(nodes) | nodes
        else:
            assert False, "Invalid axis: " + self.__axis

        if self.__test == "*":
            pass
        elif '*' in self.__test:
            nodes = set(i for i in nodes if fnmatchcase(i[0], self.__test))
        else:
            nodes = set(i for i in nodes if i[0] == self.__test)

        #print("<< evalForward", len(nodes))
        return nodes

class NotPredicate:
    def __init__(self, toks, graph):
        self.graph = graph
        assert len(toks) == 1, toks
        toks = toks[0]
        assert len(toks) == 2, toks
        assert toks[0] == 'not'
        self.op = toks[1]

    def __repr__(self):
        return "NotPredicate({})".format(self.op)

class AndPredicate:
    def __init__(self, toks, graph):
        self.graph = graph
        assert len(toks) == 1, toks
        toks = toks[0]
        assert len(toks) == 3
        assert toks[1] == 'and'
        self.left = toks[0]
        self.right = toks[2]

    def __repr__(self):
        return "AndPredicate({}, {})".format(self.left, self.right)

class OrPredicate:
    def __init__(self, toks, graph):
        self.graph = graph
        assert len(toks) == 1, toks
        toks = toks[0]
        assert len(toks) == 3
        assert toks[1] == 'or'
        self.left = toks[0]
        self.right = toks[2]

    def __repr__(self):
        return "OrPredicate({}, {})".format(self.left, self.right)


class PackageGraph:
    class FakeRoot:
        def __init__(self, childs):
            self.__childs = childs

        def getDirectDepSteps(self):
            return (i.getPackageStep() for i in self.__childs)

        def getIndirectDepSteps(self):
            return []

    def __init__(self, rootPackages):
        # build package DAG
        self.graph = {}
        self.root = ('<root>', None)
        self.__rootPackage = PackageGraph.FakeRoot(list(rootPackages.values()))
        self.graph[self.root] = node = GraphNode(set(), set())
        for (name, pkg) in rootPackages.items():
            childKey = self.__buildGraph(name, pkg, self.root)
            node.childs.add(childKey)

        # create parsing grammer
        LocationPath = pyparsing.Forward()
        RelativeLocationPath = pyparsing.Forward()

        AxisName = \
              pyparsing.Keyword("descendant-or-self") \
            | pyparsing.Keyword("ancestor-or-self") \
            | pyparsing.Keyword("child") \
            | pyparsing.Keyword("descendant") \
            | pyparsing.Keyword("parent") \
            | pyparsing.Keyword("ancestor") \
            | pyparsing.Keyword("self")

        NodeTest = pyparsing.Word(pyparsing.alphanums + "_.:+-*")
        AxisSpecifier = AxisName + '@'
        AbbreviatedStep = pyparsing.Keyword('..') | pyparsing.Keyword('.')
        PredExpr = pyparsing.infixNotation(LocationPath,
            [
                ('not', 1, pyparsing.opAssoc.RIGHT, lambda s, loc, toks: NotPredicate(toks, self.graph)),
                ('and', 2, pyparsing.opAssoc.LEFT,  lambda s, loc, toks: AndPredicate(toks, self.graph)),
                ('or',  2, pyparsing.opAssoc.LEFT,  lambda s, loc, toks: OrPredicate(toks, self.graph))
            ])
        Predicate = '[' + PredExpr + ']'
        Step = AbbreviatedStep | (pyparsing.Optional(AxisSpecifier) + NodeTest + pyparsing.Optional(Predicate))
        Step.setParseAction(lambda s, loc, toks: StepAction(toks, self.graph))
        AbbreviatedRelativeLocationPath = Step + '//' + RelativeLocationPath
        RelativeLocationPath << (AbbreviatedRelativeLocationPath | (Step + '/' + RelativeLocationPath) | Step)
        AbbreviatedAbsoluteLocationPath = '//' + RelativeLocationPath
        AbsoluteLocationPath = AbbreviatedAbsoluteLocationPath | ('/' + RelativeLocationPath)
        LocationPath << (AbsoluteLocationPath | RelativeLocationPath)
        LocationPath.setParseAction(lambda s, loc, toks: PathAction(toks, self.graph))

        self.pathGrammer = LocationPath

    def __buildGraph(self, name, pkg, parent):
        key = (name, pkg.getPackageStep().getVariantId())
        node = self.graph.get(key)
        if node is not None:
            node.parents.add(parent)
            return key

        self.graph[key] = node = GraphNode(set([parent]), set())

        for s in pkg.getDirectDepSteps():
            childPkg = s.getPackage()
            childKey = self.__buildGraph(childPkg.getName(), childPkg, key)
            node.childs.add(childKey)
        for s in pkg.getIndirectDepSteps():
            childPkg = s.getPackage()
            childKey = self.__buildGraph(childPkg.getName(), childPkg, key)
            node.childs.add(childKey)

        return key

    def __findResults(self, node, pkg, result, valid):
        nextPackages = { s.getPackage().getName() : s.getPackage()
            for s in pkg.getDirectDepSteps() }
        for s in pkg.getIndirectDepSteps():
            p = s.getPackage()
            nextPackages.setdefault(p.getName(), p)

        #print(node, nextPackages)
        #print(sorted(graph[node].childs & valid))
        for child in sorted(self.graph[node].childs & valid):
            if child in result:
                yield nextPackages[child[0]]
            yield from self.__findResults(child, nextPackages[child[0]], result, valid)

    def evalPath(self, path):
        while path.endswith('/'): path = path[:-1]
        path = self.pathGrammer.parseString(path, True)
        assert len(path) == 1
        assert isinstance(path[0], PathAction)

        #print(path)
        (nodes, valid) = path[0].evalForward(self.root)
        #print(nodes)
        #print(valid)
        #print("*****************")
        return self.__findResults(self.root, self.__rootPackage, nodes, valid)


def evalPathSpec(rootPackages, path):
    graph = PackageGraph(rootPackages)
    return graph.evalPath(path)
