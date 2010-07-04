# Copyright 2004-2010 PyTom <pytom@bishoujo.us>
#
# Permission is hereby granted, free of charge, to any person
# obtaining a copy of this software and associated documentation files
# (the "Software"), to deal in the Software without restriction,
# including without limitation the rights to use, copy, modify, merge,
# publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so,
# subject to the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
# WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

import renpy
import contextlib

# Grab the python versions of the parser and ast modules.
ast = __import__("ast")

# The filename of the file we're parsing.
filename = None

new_variable_serial = 0

# Returns the name of a new variable.
@contextlib.contextmanager
def new_variable():
    global new_variable_serial

    new_variable_serial += 1
    yield "_%d" % new_variable_serial
    new_variable_serial -= 1

def increment_lineno(node, amount):
    for node in ast.walk(node):
        if hasattr(node, 'lineno'):
            node.lineno += amount
    
class LineNumberNormalizer(ast.NodeVisitor):

    def __init__(self):
        self.last_line = 1
    
    def generic_visit(self, node):

        if not hasattr(node, 'lineno'):
            return
        
        self.last_line = max(self.last_line, node.lineno)
        node.lineno = self.last_line

        super(LineNumberNormalizer, self).generic_visit(node)
            

##############################################################################
# Parsing.

# The parser that things are being added to.
parser = None

class Positional(object):
    """
    This represents a positional parameter to a function.
    """

    def __init__(self, name):
        self.name = name

        if parser:
            parser.add(self)

# Used to generate the documentation
all_keyword_names = set()
            
class Keyword(object):
    """
    This represents an optional keyword parameter to a function.
    """
    
    def __init__(self, name):
        self.name = name
        self.style = False

        all_keyword_names.add(self.name) 
       
        if parser:
            parser.add(self)
        
class Style(object):
    """
    This represents a style parameter to a function.
    """

    def __init__(self, name):
        self.name = name
        self.style = True

        for j in renpy.style.prefix_subs:
            all_keyword_names.add(j + self.name)

        if parser:
            parser.add(self)


class Parser(object):

    def __init__(self, name):

        # The name of this object.
        self.name = name
        
        # The positional arguments, keyword arguments, and child
        # statements of this statement.
        self.positional = [ ]
        self.keyword = { }
        self.children = { }

        all_statements.append(self)

    def __repr__(self):
        return "<%s: %s>" % (self.__class__.__name__, self.name)

    def add(self, i):
        """
        Adds a clause to this parser.
        """

        if isinstance(i, list):
            for j in i:
                self.add(j)

            return
        
        if isinstance(i, Positional):
            self.positional.append(i)

        elif isinstance(i, Keyword):
            self.keyword[i.name] = i                

        elif isinstance(i, Style):
            for j in renpy.style.prefix_subs:
                self.keyword[j + i.name] = i

        elif isinstance(i, Parser):
            self.children[i.name] = i

    def parse_statement(self, l, name):
        word = l.word()

        if word and word in self.children:
            c = self.children[word].parse(l, name)
            return c
        else:            
            return None

    def parse_children(self, stmt, l, name):
        l.expect_block(stmt)

        l = l.subblock_lexer()

        rv = [ ]

        with new_variable() as child_name:

            count = 0
            
            while l.advance():

                if len(l.block) != 1:
                    rv.extend(self.parse_exec("%s = (%s, %d)" % (child_name, name, count), l.number))
                else:
                    child_name = name
                    
                c = self.parse_statement(l, child_name)
                if c is None:
                    l.error('Expected screen language statement.')

                rv.extend(c)
                count += 1
                    

        return rv
    
    def parse_eval(self, expr, lineno=1):
        """
        Parses an expression for eval, and then strips off the module
        and expr instances, and adjusts the line number.
        """

        try:
            rv = ast.parse(expr, 'eval').body[0].value
        except SyntaxError, e:            
            raise renpy.parser.ParseError(
                filename,
                lineno + e[1][1] - 1,
                "Syntax error while parsing python expression.",
                e[1][3],
                e[1][2])
            
        increment_lineno(rv, lineno-1)

        return rv

    def parse_exec(self, code, lineno=1):
        """
        Parses an expression for exec, then strips off the module and
        adjusts the line number. Returns a list of statements.
        """

        try:
            rv = ast.parse(code, 'exec')
        except SyntaxError, e:

            print repr(e)
            
            raise renpy.parser.ParseError(
                filename,
                lineno + e[1][1] - 1,
                "Syntax error while parsing python code.",
                e[1][3],
                e[1][2])
            
        increment_lineno(rv, lineno-1)

        return rv.body

    def parse_simple_expression(self, l):
        lineno = l.number
        expr = l.require(l.simple_expression)

        return self.parse_eval(expr, lineno)

    def parse(self, l, name):
        """
        This is expected to parse a function statement, and to return
        a list of python ast statements.

        `l` the lexer.

        `name` the name of the variable containing the name of the
        current statement.
        """

        raise NotImplemented()

    
            
# A singleton value.
many = object()
    
class FunctionStatementParser(Parser):
    """
    This is responsible for parsing function statements.
    """

    def __init__(self, name, function, nchildren=0, unevaluated=False):

        super(FunctionStatementParser, self).__init__(name)
        
        # Functions that are called when this statement runs.
        self.function = function

        # The number of children we have.
        self.nchildren = nchildren
        
        # True if we should evaluate arguments and children. False
        # if we should just pass them into our child.
        self.unevaluated = unevaluated

        # Add us to the appropriate lists.
        global parser
        parser = self

        if nchildren != 0:
            childbearing_statements.append(self)
            
    def parse(self, l, name):

        # The list of nodes this function returns.
        rv = [ ]

        # The line number of the current node.
        lineno = l.number
        
        func = self.parse_eval(self.function, lineno)        

        call_node = ast.Call(
            lineno=lineno,
            col_offset=0, 
            func=func,
            args=[ ],
            keywords=[ ],
            starargs=None,
            kwargs=None,
            )

        seen_keywords = set()
        
        # Parses a keyword argument from the lexer.
        def parse_keyword(l):
            name = l.word()

            if name is None:
                l.error('expected a keyword argument, colon, or end of line.')
            
            if name not in self.keyword:
                l.error('%r is not a keyword argument or valid child for the %s statement.' % (name, self.name))
            
            if name in seen_keywords:
                l.error('keyword argument %r appears more than once in a %s statement.' % (name, self.name))

            seen_keywords.add(name)

            expr = self.parse_simple_expression(l)

            call_node.keywords.append(
                ast.keyword(arg=name, value=expr),
                )
                
        # We assume that the initial keyword has been parsed already,
        # so we start with the positional arguments.

        for i in self.positional:
            call_node.args.append(self.parse_simple_expression(l))

        # Next, we allow keyword arguments on the starting line.
        while True:
            if l.match(':'):
                l.expect_eol()
                l.expect_block(self.name)
                block = True
                break

            if l.eol():
                l.expect_noblock(self.name)
                block = False
                break

            parse_keyword(l)

        rv.append(ast.Expr(value=call_node))

        if self.nchildren == 1:
            rv.extend(self.parse_exec('ui.child_or_fixed()'))

        # The index of the child we're adding to this statement.
        child_index = 0

        # The variable we store the child's name in.
        with new_variable() as child_name:
        
            # If we have a block, then parse each line.
            if block:

                l = l.subblock_lexer()

                while l.advance():

                    state = l.checkpoint()

                    c = self.parse_statement(l, child_name)
                    if c is not None:

                        rv.extend(self.parse_exec("%s = (%s, %d)" % (child_name, name, child_index)))
                        rv.extend(c)

                        child_index += 1

                        continue

                    l.revert(state)

                    while not l.eol():
                        parse_keyword(l)

        if self.nchildren != 0:
            rv.extend(self.parse_exec("ui.close()"))        

        if "id" not in seen_keywords:
            call_node.keywords.append(ast.keyword(arg="id", value=self.parse_eval(name, lineno)))
            
        return rv

        
##############################################################################
# Definitions of screen language statements.

# Used to allow statements to take styles.
styles = [ ]

# All statements defined, and statements that take children.
all_statements = [ ]
childbearing_statements = [ ]

position_properties = [ Style(i) for i in [
        "anchor",
        "xanchor",
        "yanchor",
        "pos",
        "xpos",
        "ypos",
        "align",
        "xalign",
        "yalign",
        "xoffset",
        "yoffset",
        "xmaximum",
        "ymaximum",
        "area",
        "clipping",
        ] ]

text_properties = [ Style(i) for i in [
        "antialias",
        "black_color",
        "bold",
        "color",
        "drop_shadow",
        "drop_shadow_color",
        "first_indent",
        "font",
        "size",
        "italic",
        "justify",
        "language",
        "layout",
        "line_spacing",
        "minwidth",
        "min_width",
        "outlines",
        "rest_indent",
        "slow_cps",
        "slow_cps_multiplier",
        "slow_abortable",
        "text_align",
        "text_y_fudge",
        "underline",
        "xmaximum",
        "ymaximum",
        "xminimum",
        "yminimum",
        "xfill",
        "yfill",
        ] ]

window_properties = [ Style(i) for i in [
        "background",
        "foreground",
        "left_margin",
        "right_margin",
        "bottom_margin",
        "top_margin",
        "xmargin",
        "ymargin",
        "left_padding",
        "right_padding",
        "top_padding",
        "bottom_padding",
        "xpadding",
        "ypadding",
        "size_group",
        "xminimum",
        "yminimum",
        "xfill",
        "yfill",
        ] ]

button_properties = [ Style(i) for i in [
        "sound",
        "mouse",
        ] ]

bar_properties = [ Style(i) for i in [
        "bar_vertical",
        "bar_invert"
        "bar_resizing",
        "left_gutter",
        "right_gutter",
        "top_gutter",
        "bottom_gutter",
        "left_bar",
        "right_bar",
        "top_bar",
        "bottom_bar",
        "thumb",
        "thumb_shadow",
        "thumb_offset",
        "mouse",
        "unscrollable",
        ] ]

box_properties = [ Style(i) for i in [
        "box_layout",
        "spacing",
        "first_spacing",
        "xfill",
        "yfill",
        ] ]

ui_properties = [
    Keyword("at"),
    Keyword("id"),
    Keyword("style"),
    ]


def add(thing):
    parser.add(thing)

    
##############################################################################
# UI statements.

FunctionStatementParser("null", "ui.null", 0)
Keyword("width")
Keyword("height")
add(ui_properties)
add(position_properties)


FunctionStatementParser("text", "ui.text", 0)
Positional("text")
Keyword("slow")
add(ui_properties)
add(position_properties)
add(text_properties)

FunctionStatementParser("hbox", "ui.hbox", many)
add(ui_properties)
add(position_properties)
add(box_properties)

FunctionStatementParser("vbox", "ui.vbox", many)
add(ui_properties)
add(position_properties)
add(box_properties)

FunctionStatementParser("fixed", "ui.fixed", many)
add(ui_properties)
add(position_properties)
add(box_properties)

FunctionStatementParser("grid", "ui.grid", many)
Positional("cols")
Positional("rows")
Keyword("transpose")
add(ui_properties)
add(position_properties)

FunctionStatementParser("side", "ui.side", many)
Positional("positions")
add(ui_properties)
add(position_properties)

# Omit sizer, as we can always just put an xmaximum and ymaximum on an item.

for name in [ "window", "frame" ]:
    FunctionStatementParser(name, "ui." + name, 1)
    add(ui_properties)
    add(position_properties)
    add(window_properties)

FunctionStatementParser("key", "ui.key", 0)
Positional("key")
Keyword("action")

FunctionStatementParser("timer", "ui.timer", 0)
Positional("delay")
Keyword("action")
Keyword("repeat")

# Omit behaviors.
# Omit menu as being too high-level.

FunctionStatementParser("input", "ui.input", 0)
Keyword("default")
Keyword("length")
Keyword("allow")
Keyword("exclude")
Keyword("prefix")
Keyword("suffix")
Keyword("changed")
add(ui_properties)
add(position_properties)
add(text_properties)

FunctionStatementParser("image", "ui.image", 0)
Positional("im")

# Omit imagemap_compat for being too high level (and obsolete).

FunctionStatementParser("button", "ui.button", 1)
Keyword("action")
Keyword("clicked")
Keyword("hovered")
Keyword("unhovered")
add(ui_properties)
add(position_properties)
add(window_properties)
add(button_properties)

FunctionStatementParser("imagebutton", "ui.imagebutton", 0)
Keyword("auto")
Keyword("idle")
Keyword("hover")
Keyword("insensitive")
Keyword("selected_idle")
Keyword("selected_hover")
Keyword("action")
Keyword("clicked")
Keyword("hovered")
Keyword("unhovered")
Keyword("image_style")
add(ui_properties)
add(position_properties)
add(window_properties)
add(button_properties)

FunctionStatementParser("textbutton", "ui.textbutton", 0)
Positional("label")
Keyword("action")
Keyword("clicked")
Keyword("hovered")
Keyword("unhovered")
Keyword("text_style")
add(ui_properties)
add(position_properties)
add(window_properties)
add(button_properties)

for name in [ "bar", "vbar" ]:
    FunctionStatementParser(name, "ui." + name, 0)    
    Keyword("adjustment")
    Keyword("range")
    Keyword("value")
    Keyword("changed")
    add(ui_properties)
    add(position_properties)
    add(bar_properties)
    
# Omit autobar. (behavior)

FunctionStatementParser("viewport", "ui.viewport", 1)
Keyword("child_size")
Keyword("mousewheel")
Keyword("draggable")
Keyword("xadjustment")
Keyword("yadjustment")
add(ui_properties)
add(position_properties)

# Omit conditional. (behavior)

FunctionStatementParser("imagemap", "ui.imagemap", many)
Keyword("ground")
Keyword("hover")
Keyword("insensitive")
Keyword("idle")
Keyword("selected_hover")
Keyword("selected_idle")
Keyword("auto")
add(ui_properties)
add(position_properties)

FunctionStatementParser("hotspot", "ui.hotspot_with_child", 1)
Positional("spot")
Keyword("action")
Keyword("clicked")
Keyword("hovered")
Keyword("unhovered")
add(ui_properties)
add(position_properties)
add(window_properties)
add(button_properties)

FunctionStatementParser("hotbar", "ui.hotbar", 0)
Positional("spot")
Keyword("adjustment")
Keyword("range")
Keyword("value")
add(ui_properties)
add(position_properties)
add(bar_properties)


FunctionStatementParser("transform", "ui.transform", 1)
Keyword("at")
Keyword("id")
for i in renpy.atl.PROPERTIES:
    Style(i)

FunctionStatementParser("add", "ui.add", 0)
Positional("im")
Keyword("at")
Keyword("id")
for i in renpy.atl.PROPERTIES:
    Style(i)

FunctionStatementParser("on", "ui.on", 0)
Positional("event")
Keyword("action")

    

##############################################################################
# Control-flow statements.

def PassParser(Parser):

    def __init__(self, name):
        super(PassParser, self).__init__(name)

    def parse(self, l, name):
        return [ ast.Pass(lineno=l.number, col_offset=0) ]

PassParser("pass")
        

class UseParser(Parser):

    def __init__(self, name):
        super(UseParser, self).__init__(name)
        childbearing_statements.append(self)
        
    def parse(self, l, name):

        lineno = l.number
        
        target_name = l.require(l.word)

        code = "renpy.use_screen(%r, _name=%s, _scope=_scope" % (target_name, name)
        
        args = renpy.parser.parse_arguments(l)

        if args:

            for k, v in args.arguments:
                if k is None:
                    l.error('The use statement only takes keyword arguments.')
                    
                code += ", %s=(%s)" % (k, v)
                    
            if args.extrapos:
                l.error('The use statement only takes keyword arguments.')

            if args.extrakw:
                code += ", **(%s)" % args.extrakw
                
        code += ")"

        return self.parse_exec(code, lineno)

UseParser("use")


class IfParser(Parser):

    def __init__(self, name):
        super(IfParser, self).__init__(name)
        childbearing_statements.append(self)

    def parse(self, l, name):
        
        with new_variable() as child_name:

            count = 0
            
            lineno = l.number
            condition = self.parse_eval(l.require(l.python_expression), lineno)

            l.require(':')
            l.expect_eol()
            
            body = self.parse_exec("%s = (%s, %d)" % (child_name, name, count))
            body.extend(self.parse_children('if', l, child_name))

            orelse = [ ]
            
            rv = ast.If(test=condition, body=body, orelse=orelse, lineno=lineno, col_offset=0)

            count += 1
            
            while l.advance():

                old_orelse = orelse
                lineno = l.number
                
                state = l.checkpoint()

                if l.keyword("elif"):
                    condition = self.parse_eval(l.require(l.python_expression), lineno)

                    body = self.parse_exec("%s = (%s, %d)" % (child_name, name, count))
                    body.extend(self.parse_children('if', l, child_name))

                    orelse = [ ]
                    old_orelse.append(ast.If(test=condition, body=body, orelse=orelse, lineno=lineno, col_offset=0))

                    count += 1

                elif l.keyword("else"):

                    old_orelse.extend(self.parse_exec("%s = (%s, %d)" % (child_name, name, count)))
                    old_orelse.extend(self.parse_children('if', l, child_name))

                    break
                    
                else:
                    l.revert(state)
                    break

        return [ rv ]

IfParser("if")


class ForParser(Parser):
        
    def __init__(self, name):
        super(ForParser, self).__init__(name)
        childbearing_statements.append(self)

    def parse_tuple_pattern(self, l):

        is_tuple = False
        pattern = [ ]
        
        while True:

            lineno = l.number
                
            if l.match(r"\("):
                p = self.parse_tuple_pattern(l)
            else:
                p = l.name().encode("latin-1")

            if not p:
                break

            pattern.append(ast.Name(id=p, ctx=ast.Store(), lineno=lineno, col_offset=0))

            if l.match(r","):
                is_tuple = True
            else:
                break

        if not pattern:
            l.error("Expected tuple pattern.")

        if not is_tuple:
            return pattern[0]
        else:
            return ast.Tuple(elts=pattern, ctx=ast.Store())
        
    def parse(self, l, name):

        lineno = l.number

        pattern = self.parse_tuple_pattern(l)

        l.require('in')

        expression = self.parse_eval(l.require(l.python_expression), l.number)
                
        l.require(':')
        l.expect_eol()

        with new_variable() as counter_name:
        
            with new_variable() as child_name:

                children = self.parse_exec("%s = (%s, %s)" % (child_name, name, counter_name))
                children.extend(self.parse_children('for', l, child_name))
                children.extend(self.parse_exec("%s += 1" % counter_name))
                
            rv = self.parse_exec("%s = 0" % counter_name)

            rv.append(ast.For(
                    target=pattern,
                    iter=expression,
                    body=children,
                    orelse=[],
                    lineno=lineno,
                    col_offset=0))

        return rv
            
ForParser("for")            


class PythonParser(Parser):
        
    def __init__(self, name, one_line):
        super(PythonParser, self).__init__(name)

        self.one_line = one_line

    def parse(self, l, name):
        lineno = l.number

        if self.one_line:
            python_code = l.rest()
            l.expect_noblock('one-line python statement')
        else:
            l.require(':')
            l.expect_block('python block')

            python_code = l.python_block()
            lineno += 1
            
        return self.parse_exec(python_code, lineno)

PythonParser("$", True)
PythonParser("python", False)


##############################################################################
# Add all_statements to the statements that take children.

for i in childbearing_statements:
    i.add(all_statements)

##############################################################################
# Definition of the screen statement.

# class ScreenFunction(renpy.object.Object):

#     def __init__(self, children):
#         self.children = children

#     def __call__(self, _name=(), _scope=None, **kwargs):

#         for i, child in enumerate(self.children):
#             child.evaluate(_name + (i,), _scope)
    
# def screen_function(positional, keyword, children):
#     name = renpy.python.py_eval(positional[0].source)
#     function = ScreenFunction(children)

#     values = {
#         "name" : name,
#         "function" : function,
#         }

#     for k, v in keyword.iteritems():
#         values[k] = renpy.python.py_eval(v.source)

#     return values

    
# screen_stmt = FunctionStatementParser("screen", screen_function, unevaluated=True)
# Positional("name", Word)
# Keyword("modal", Expression)
# Keyword("zorder", Expression)
# Keyword("tag", Word)
# add(all_statements)

class ScreenLangScreen(renpy.object.Object):
    """
    This represents a screen defined in the screen language.
    """

    def __init__(self):

        # The name of the screen.
        self.name = name

        # Should this screen be declared as modal?
        self.modal = False

        # The screen's zorder.
        self.zorder = 0

        # The screen's tag.
        self.tag = None
        
        # The PyCode object containing the screen's code.
        self.code = None
        

    def define(self):
        """
        Defines us as a screen.
        """

        renpy.display.screen.define_screen(
            self.name,
            self,
            modal=self.modal,
            zorder=self.zorder,
            tag=self.tag)

    def __call__(self, _scope=None, **kwargs):
        renpy.python.py_exec_bytecode(self.code.bytecode, locals=_scope)
        

class ScreenParser(Parser):

    def __init__(self):
        super(ScreenParser, self).__init__("screen")
        
    def parse(self, l, name="_name"):

        screen = ScreenLangScreen()

        def parse_keyword(l):
            if l.match('modal'):
                screen.modal = eval(l.require(l.simple_expression))
                return True

            if l.match('zorder'):
                screen.zorder = eval(l.require(l.simple_expression))
                return True

            if l.match('tag'):
                screen.tag = l.require(l.word)
                return True

            return False

        
        lineno = l.number
        
        screen.name = l.require(l.word)

        while parse_keyword(l):
            continue

        l.require(':')
        l.expect_eol()        
        l.expect_block('screen statement')

        l = l.subblock_lexer()

        rv = [ ]
        count = 0
        
        with new_variable() as child_name:

            while l.advance():

                if parse_keyword(l):
                    while parse_keyword(l):
                        continue

                    l.expect_eol()
                    continue

                rv.extend(self.parse_exec("%s = (%s, %d)" % (child_name, name, count), l.number))

                c = self.parse_statement(l, child_name)

                if c is None:
                    l.error('Expected a screen language statement.')
                
                rv.extend(c)

        node = ast.Module(body=rv, lineno=lineno, col_offset=0)
        ast.fix_missing_locations(node)
        LineNumberNormalizer().visit(node)

        screen.code = renpy.ast.PyCode(node, (l.get_location()[0], lineno), 'exec')

        return screen
                
screen_parser = ScreenParser()
screen_parser.add(all_statements)

def parse_screen(l):
    """
    Parses the screen statement.
    """

    global filename

    filename = l.filename
    
    screen = screen_parser.parse(l)
    return screen
