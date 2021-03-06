#!/usr/bin/env python

"""
Copyright 2017 ThoughtSpot

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated 
documentation files (the "Software"), to deal in the Software without restriction, including without limitation the 
rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to 
permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions 
of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED 
TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE 
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, 
TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""
from __future__ import print_function
import sys
import argparse
import csv
import os.path
import subprocess
import time
from subprocess import check_output


"""
Delete records from tables based on a CSV document.  
Each line of the description file has the following format:  table_name, col1, col2, etc.
Each line of the data file has the following format: table_name, val1, val2, etc.
The delete will be of the format DELETE FROM table_name WHERE col1 = val1 AND col2 = val2, etc.
   
ASSUMPTIONS:
  * the format of TQL output will not change
  * this script will be run on the appliance and be able to call TQL to execute delete commands.
  * fields do not contain the separator value.
"""


def main():
    """
    Reads a description file for what to delete and then deletes the appropriate records.
    """
    args = parse_args()
    if check_args(args):
        read_descriptions(args)
        generate_deletes(args)


def parse_args():
    """
    Parse the command line arguments.
    :return: An args dictionary with command line arguments.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-f", "--filename", help="path to file with records to delete"
    )
    parser.add_argument(
        "-t", "--table", help="name of the table to delete records from"
    )
    parser.add_argument("-d", "--database", help="database to delete from")
    parser.add_argument(
        "-s",
        "--schema",
        default="falcon_default_schema",
        help="schema to delete from",
    )
    parser.add_argument(
        "-p", "--separator", default="|", help="separator to use in data"
    )
    args = parser.parse_args()
    return args


# description of the tables in the database.
# { table1 : { column_name : type, ... }, table2 : { column_name : type, ...} }
descriptions = {}


def check_args(args):
    args_are_good = True

    if args.filename is None or os.path.isfile(args.filename) is False:
        eprint("Delete file %s was not found." % args.filename)
        args_are_good = False

    if args.table is None:
        eprint("Table was not specified.")
        args_are_good = False

    if args.database is None:
        eprint("Database was not specified.")
        args_are_good = False

    return args_are_good


def read_descriptions(args):
    """
    Reads the table descriptions from the database schema and populates the descriptions.
    WARNING:  This depends on the format of tql output not changing.
    :param args: Command line arguments.
    """

    table_list = check_output(
        'echo "show tables %s;" | tql' % args.database, shell=True
    ).split(
        "\n"
    )
    for table in table_list:
        table_details = table.split("|")
        if len(table_details) >= 2:
            schema_name = table_details[0].strip()
            table_name = table_details[1].strip()

            schema = descriptions.get(schema_name, None)
            if schema is None:
                schema = {}

            table = schema.get(table_name, None)
            if table is None:
                table = {}

            column_list = check_output(
                'echo "show table %s.%s.%s;" | tql'
                % (args.database, schema_name, table_name),
                shell=True,
            ).split(
                "\n"
            )
            for column in column_list:
                column_details = column.split("|")
                if len(column_details) >= 2:
                    column_name = column_details[0].strip()
                    column_type = column_details[2].strip()
                    table[column_name] = column_type

            schema[table_name] = table
            descriptions[schema_name] = schema


# print (descriptions)


def generate_deletes(args):
    """
    Creates and executes the delete statements from from the values file.
    :param args: Command line arguments.
    """
    start = time.time()
    nbr_deletes = 0

    # get the column descriptions.
    columns = descriptions.get(args.schema, {}).get(args.table, None)

    if columns is None:
        eprint("Table %s.%s not found." % (args.schema, args.table))
        return

    tmpfile = "/tmp/deleteme"
    with open(args.filename, "rb") as valuefile:
        filereader = csv.DictReader(valuefile, delimiter="|", quotechar='"')
        with open(tmpfile, "w") as deletefile:
            for values in filereader:
                delete_stmt = "DELETE FROM %s.%s.%s WHERE " % (
                    args.database, args.schema, args.table
                )

                first = True
                for key in values.keys():
                    if not first:
                        delete_stmt += " AND "
                    else:
                        first = False

                    # TODO see if I need to un-quote non-numeric.  Might need to re-do desc file.
                    if "int" in columns[key] or "double" in columns[key]:
                        delete_stmt += ("%s = %s" % (key, values[key]))
                    else:
                        delete_stmt += ("%s = '%s'" % (key, values[key]))

                delete_stmt += ";\n"
                deletefile.write(delete_stmt)
                nbr_deletes += 1

    subprocess.call("cat %s | tql" % tmpfile, shell=True)

    finish = time.time()
    print(
        "Executed %d deletes in %s seconds." % (nbr_deletes, (finish - start))
    )


def eprint(*args, **kwargs):
    """Prints to standard error"""
    print(*args, file=sys.stderr, **kwargs)


if __name__ == "__main__":
    main()
