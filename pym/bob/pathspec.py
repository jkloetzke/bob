
from collections import namedtuple
from fnmatch import fnmatchcase
import pyparsing

# nodes of name graph
GraphNode = namedtuple('GraphNode', ['pkg', 'parents', 'childs'])

# parsing grammer
RelativeLocationPath = pyparsing.Forward()
AxisName = pyparsing.Keyword("child") \
    | pyparsing.Keyword("descendant") \
    | pyparsing.Keyword("parent") \
    | pyparsing.Keyword("ancestor") \
    | pyparsing.Keyword("self") \
    | pyparsing.Keyword("descendant-or-self") \
    | pyparsing.Keyword("ancestor-or-self")
NodeTest = pyparsing.Word(pyparsing.alphanums + "_.:+-*")
AxisSpecifier = AxisName + '@'
AbbreviatedStep = pyparsing.Keyword('..') | pyparsing.Keyword('.')
Step = AbbreviatedStep | (pyparsing.Optional(AxisSpecifier) + NodeTest)
AbbreviatedRelativeLocationPath = pyparsing.Group(Step) + '//' + pyparsing.Group(RelativeLocationPath)
RelativeLocationPath << (AbbreviatedRelativeLocationPath | (pyparsing.Group(Step) + '/' + pyparsing.Group(RelativeLocationPath)) | pyparsing.Group(Step))
AbbreviatedAbsoluteLocationPath = '//' + pyparsing.Group(RelativeLocationPath)
AbsoluteLocationPath = AbbreviatedAbsoluteLocationPath | ('/' + pyparsing.Group(RelativeLocationPath))
LocationPath = AbsoluteLocationPath | RelativeLocationPath


def _buildGraph(graph, name, pkg, parent):
    key = (name, pkg.getPackageStep().getVariantId())
    node = graph.get(key)
    if node is not None:
        node.parents.add(parent)
        return key

    graph[key] = node = GraphNode(pkg, set(), set())

    for s in pkg.getDirectDepSteps():
        childPkg = s.getPackage()
        childKey = _buildGraph(graph, childPkg.getName(), childPkg, key)
        node.childs.add(childKey)
    for s in pkg.getIndirectDepSteps():
        childPkg = s.getPackage()
        childKey = _buildGraph(graph, childPkg.getName(), childPkg, key)
        node.childs.add(childKey)

    return key

def buildGraph(rootPackages):
    graph = {}
    key = ('<root>', None)
    graph[key] = node = GraphNode(None, set(), set())
    for (name, pkg) in rootPackages.items():
        childKey = _buildGraph(graph, name, pkg, key)
        node.childs.add(childKey)
    return (key, graph)


def evalAxisChild(graph, nodes):
    ret = set()
    for i in nodes:
        ret.update(graph[i].childs)
    return ret

def evalAxisDescendant(graph, nodes):
    ret = set()
    todo = nodes
    while todo:
        childs = set()
        for i in todo: childs.update(graph[i].childs)
        todo = childs - ret
        ret.update(childs)
    return ret

def evalAxisParent(graph, nodes):
    ret = set()
    for i in nodes:
        ret.update(graph[i].parents)
    return ret

def evalAxisAncestor(graph, nodes):
    ret = set()
    todo = nodes
    while todo:
        parents = set()
        for i in todo: parents.update(graph[i].parents)
        todo = parents - ret
        ret.update(parents)
    return ret

def evalPathStep(graph, step, nodes):
    if len(step) == 1:
        if step[0] == '.':
            axis = 'self'
            test = '*'
        elif step[0] == '..':
            axis = 'parent'
            test = '*'
        else:
            axis = 'child'
            test = step[0]
    else:
        axis = step[0]
        assert step[1] == '@'
        test = step[2]

    #print(">> evalPathStep", axis, test, len(nodes))

    if axis == "child":
        nodes = evalAxisChild(graph, nodes)
    elif axis == "descendant":
        nodes = evalAxisDescendant(graph, nodes)
    elif axis == "parent":
        nodes = evalAxisParent(graph, nodes)
    elif axis == "ancestor":
        nodes = evalAxisAncestor(graph, nodes)
    elif axis == "self":
        pass
    elif axis == "descendant-or-self":
        nodes = evalAxisDescendant(graph, nodes) | nodes
    elif axis == "ancestor-or-self":
        nodes = evalAxisAncestor(graph, nodes) | nodes
    else:
        assert False, "Invalid axis: " + axis

    if test == "*":
        pass
    elif '*' in test:
        nodes = set(i for i in nodes if fnmatchcase(i[0], test))
    else:
        nodes = set(i for i in nodes if i[0] == test)

    #print("<< evalPathStep", len(nodes))
    return nodes

def evalPathSegment(graph, nodes, path):
    if len(path) == 1:
        # last segment
        return evalPathStep(graph, path[0], nodes)
    else:
        # intermediate segment, fixup descendant-or-self
        if path[1] == '//':
            path[1] = '/'
            path[2] = [['descendant-or-self', '@', '*'], '/', path[2]]
        assert path[1] == '/'
        return evalPathSegment(graph, evalPathStep(graph, path[0], nodes), path[2])

def evalPathSpec(rootPackages, path):
    while path.endswith('/'): path = path[:-1]
    path = LocationPath.parseString(path, True)
    (root, graph) = buildGraph(rootPackages)
    if len(path) == 2:
        if path[0] == '//':
            roots = set(graph.keys())
        else:
            roots = set([root])
        path = path[1]
    else:
        roots = set([root])

    print(path)
    nodes = evalPathSegment(graph, roots, path)
    return (graph[n].pkg for n in sorted(nodes))
