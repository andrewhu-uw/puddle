import networkx as nx
import yaml

from attr import dataclass
from typing import Tuple, Any, ClassVar, List, Dict, Set

from puddle.util import pairs

import logging
log = logging.getLogger(__name__)


Location = Tuple[int, int]


# disable generation of cmp so it uses id-based hashing
@dataclass(cmp=False)
class Droplet:

    info: Any
    locations: Set[Location]
    valid: bool = True

    def to_dict(self):
        """ Used to JSONify this for rendering in the client """
        (loc,) = self.locations
        y,x = loc
        return {
            'id': id(self),
            'y': y,
            'x': x,
            'info': self.info,
        }

    def copy(self):
        return self.__class__(self.info, self.locations)

    def split(self, ratio=0.5):
        assert self.valid
        a = self.copy()
        b = self.copy()
        self.valid = False
        return a, b

    def mix(self, other: 'Droplet'):
        log.debug(f'mixing {self} with {other}')
        assert self.valid
        assert other.valid

        # for now, they much be in the same place
        # assert self.cell is other.cell
        # FIXME right now we assume cells only have one droplet

        self.valid  = False
        other.valid = False
        info = f'({self.info}, {other.info})'

        return Droplet(info, self.locations | other.locations)


@dataclass
class Cell:
    pin: int
    location: Location


class Command:
    shape: ClassVar[nx.DiGraph]
    input_locations: ClassVar[List[Location]]
    input_droplets: List[Droplet]
    result: Any

    strict: ClassVar[bool] = False

    def run(self, mapping: Dict[Location, Location]): ...


class Move(Command):
    input_locations: ClassVar = [(0,0)]

    def __init__(self, arch, droplet, location):
        self.arch = arch
        self.location = location
        self.input_droplets = [droplet]

    def run(self, mapping):
        pass


class Mix(Command):

    shape: ClassVar = nx.DiGraph(nx.grid_2d_graph(2, 3))
    input_locations: ClassVar = [(0,0), (0,0)]

    n_mix_loops = 1
    loop = [(0,0), (1,0), (1,1), (1,2), (0,2), (0,1), (0,0)]

    def __init__(self, arch, droplet1, droplet2):
        self.arch = arch
        self.droplet1 = droplet1
        self.droplet2 = droplet2
        self.input_droplets = [droplet1, droplet2]

    def run(self, mapping):

        # use the mapping to get the edges in the architecture we have to take
        arch_loop_edges = list(pairs(mapping[node] for node in self.loop))

        assert self.droplet1.locations == self.droplet2.locations

        self.arch.remove_droplet(self.droplet1)
        self.arch.remove_droplet(self.droplet2)
        result = Droplet.mix(self.droplet1, self.droplet2)
        self.arch.add_droplet(result)

        self.arch.wait()
        for _ in range(self.n_mix_loops):
            for src, dst in arch_loop_edges:
                result.locations = {dst}
                self.arch.wait()

        return result


class Split(Command):

    shape: ClassVar = nx.DiGraph(nx.grid_2d_graph(1,5))
    input_locations: ClassVar = [(0,2)]
    strict: ClassVar = True

    def __init__(self, arch, droplet):
        self.arch = arch
        self.droplet = droplet
        self.input_droplets = [droplet]

    def run(self, mapping):

        # use the mapping to get the edges in the architecture we have to take
        nodes1 = [(0,2), (0,1), (0,0)]
        nodes2 = [(0,2), (0,3), (0,4)]

        self.arch.remove_droplet(self.droplet)
        d1, d2 = self.droplet.split()
        # For these adds we are okay with adjacent droplets
        self.arch.add_droplet(d1)
        try:
            self.arch.add_droplet(d2)
        except CollisionError:
            log.debug('collision on splitting into drop 2')

        for n1, n2 in zip(nodes1, nodes2):
            d1.locations = {mapping[n1]}
            d2.locations = {mapping[n2]}
            self.arch.wait()

        return d1, d2


class CollisionError(Exception):
    pass


class ArchitectureError(Exception):
    pass


class Architecture:
    """ An interface to a (maybe) physical board. """

    def __init__(self, graph):

        # only directed, single-edge graphs supported
        if type(graph) is nx.Graph:
            graph = nx.DiGraph(graph)
        assert type(graph) is nx.DiGraph

        self.source_file = None

        # only works for graphs with nodes (y, x)
        assert all(len(n) == 2 for n in graph)

        ys, xs = zip(*graph)

        self.y_min, self.y_max = min(ys), max(ys)
        self.x_min, self.x_max = min(xs), max(xs)

        self.height = self.y_max - self.y_min + 1
        self.width  = self.x_max - self.x_min + 1

        self.graph = graph

        # for visualization
        self.active_commands = []
        self.session = None

        self.droplets: Set[Droplet] = set()

    def __str__(self):
        return '\n'.join(
            str(cell)
            for cell in self.cells()
            if cell.droplet
        )

    def get_droplet(self, location):
        for droplet in self.droplets:
            if location in droplet.locations:
                return droplet
        return None

    def add_droplet(self, droplet: Droplet):
        assert droplet not in self.droplets
        self.droplets.add(droplet)
        self.check_collisions()

    def remove_droplet(self, droplet: Droplet):
        assert droplet in self.droplets
        self.droplets.remove(droplet)

    def check_collisions(self):
        """
        Checks for single-cell collisions. Adjacency of cells also counts
        as a collision.
        Throws a CollisionError if there is collision on the board.
        """
        for droplet in self.droplets:
            (location,) = droplet.locations
            for other in self.droplets:
                if droplet is other:
                    continue

                (other_location,) = other.locations
                if abs(location[0] - other_location[0]) <= 1 and abs(location[1] - other_location[1]) <= 1:
                    raise CollisionError('Multiple droplets colliding')
                    log.debug('colliding')

    def cells(self):
        return (data['cell'] for _, data in self.graph.nodes(data=True))

    def wait(self):

        # print(self.spec_string(with_droplets=True))

        # self.check_invariants()

        if self.session and self.session.rendered:
            event = self.session.rendered
            if event:
                event.wait()
                event.clear()

    def push_command(self, command):
        self.active_commands.append(command)

    def pop_command(self):
        self.active_commands.pop()

    @classmethod
    def from_string(cls, string, **kwargs):
        """ Parse an arch specification string to create an Architecture.

        Arch specification strings are newline-separated and contain periods (`.`)
        for electrodes, `I` for input electrodes, and `H` for heaters. Spots where
        there are no electrodes are given by a space (` `).

        Example:
        .....
        I......H
        .....
        """

        data = yaml.load(string)
        board = data['board']

        h = len(board)
        w = max(len(row) for row in board)

        empty_values = ['_', None]

        # cells keyed by id
        cells = {}

        locs_to_add = []

        for y, row in enumerate(board):
            for x, elem in enumerate(row):
                if elem in empty_values:
                    continue

                if type(elem) is int:
                    id = elem
                    if id in cells:
                        raise ArchitectureError("Duplicate ids in arch file")
                    cells[id] = Cell(id, (y,x))

                elif elem == 'a':
                    locs_to_add.append((y,x))

                else:
                    raise ArchitectureError("Unrecognized board element '{}'".format(elem))

        try_id = 0
        for loc in locs_to_add:
            while try_id in cells:
                try_id += 1

            assert try_id not in cells
            cells[try_id] = Cell(try_id, loc)

        # make sure ids are consecutive from 0
        assert set(cells.keys()) == set(range(len(cells)))

        locs = set(c.location for c in cells.values())

        graph = nx.grid_2d_graph(h, w)
        graph.remove_nodes_from([n for n in graph if n not in locs])

        for cell in cells.values():
            graph.node[cell.location]['cell'] = cell

        return cls(graph, **kwargs)

    @classmethod
    def from_file(cls, filename, **kwargs):
        with open(filename) as f:
            string = f.read()

        arch = cls.from_string(string, **kwargs)
        arch.source_file = filename
        return arch

    def to_yaml_string(self, with_droplets=False):
        """ Dump the Architecture to YAML string. """

        lines = [ [' '] * self.width for _ in range(self.height) ]

        for cell in self.cells():
            r,c = cell.location
            if with_droplets and cell.droplet:
                lines[r][c] = 'o'
            else:
                lines[r][c] = cell.symbol

        return "\n".join("".join(line).rstrip() for line in lines) + "\n"
