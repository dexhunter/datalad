# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Utilities required by runner-related functionality

All runner-related code imports from here, so this is a comprehensive declaration
of utility dependencies.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Optional

__docformat__ = "numpy"

logger = logging.getLogger("datalad.runner.utils")


class LineSplitter:
    """
    A line splitter that handles 'streamed content' and is based
    on python's built-in splitlines().
    """
    def __init__(self,
                 separator: Optional[str] = None,
                 keep_ends: bool = False
                 ) -> None:
        """
        Create a line splitter that will split lines either on a given
        separator, if 'separator' is not None, or on one of the known line
        endings, if 'separator' is None, the line endings are determined by
        python, they include, for example, "\n", and "\r\n".

        Parameters
        ----------
        separator: Optional[str]
            If not None, the provided separator will be used to split lines.
        keep_ends: bool
            If True, the separator will be contained in the returned lines.
        """
        self.separator = separator
        self.keep_ends = keep_ends
        self.remaining_data: str | None = None

    def process(self,
                data: str
                ) -> list[str]:

        assert isinstance(data, str), f"data ({data}) is not of type str"

        # There is nothing to do if we do not get any data, since
        # remaining data would not change, and if it is not None,
        # it has already been parsed.
        if data == "":
            return []

        separator = self.separator
        # Detach the remaining data from the instance, so that it is only
        # referenced locally and CPython can extend it in place instead of
        # copying it, while a line stays unterminated over many chunks.
        remaining, self.remaining_data = self.remaining_data or "", None
        if separator is None:
            # If no separator was specified, use python's built in
            # line split wisdom to split on any known line ending. The
            # remaining data never ends with a line ending, so joining it
            # with data cannot create a new one, and only data is split.
            lines = data.splitlines(self.keep_ends)
            # All line boundaries are unprintable, so the cheap check on
            # the last character spares the costly one in most chunks.
            last = data[-1]
            terminated = not last.isprintable() and last.splitlines() != [last]
        else:
            # Only the tail of the remaining data can hold the start of a
            # separator that is completed by data, so split just that tail
            # and data, and prepend the rest to the first line.
            start = max(len(remaining) - len(separator) + 1, 0)
            lines = (remaining[start:] + data).split(separator)
            remaining = remaining[:start]
            terminated = data.endswith(separator)
            if terminated:
                # Drop the empty element that split() yields after the
                # final separator, splitlines() yields none.
                lines.pop()

        # An unterminated last line is kept for the next round.
        remaining += lines[0]
        lines[0] = remaining
        if not terminated:
            self.remaining_data = lines.pop()

        if self.keep_ends and separator is not None:
            return [line + separator for line in lines]
        return lines

    def finish_processing(self) -> Optional[str]:
        return self.remaining_data


class AssemblingDecoderMixIn:
    """ Mix in to safely decode data that is delivered in parts

    This class can be used to decode data that is partially delivered.
    It detects partial encodings and stores the non-decoded data to
    combine it with additional data, that is delivered later,  and
    decodes the combined data.

    Any un-decoded data is stored in the 'remaining_data'-attribute.
    """
    def __init__(self) -> None:
        self.remaining_data: dict[int, bytes] = defaultdict(bytes)

    def decode(self,
               fd: int,
               data: bytes,
               encoding: str
               ) -> str:
        assembled_data = self.remaining_data[fd] + data
        try:
            unicode_str = assembled_data.decode(encoding)
            self.remaining_data[fd] = b''
        except UnicodeDecodeError as e:
            unicode_str = assembled_data[:e.start].decode(encoding)
            self.remaining_data[fd] = assembled_data[e.start:]
        return unicode_str

    def __del__(self) -> None:
        if any(self.remaining_data.values()):
            logger.debug(
                "unprocessed data in AssemblingDecoderMixIn:\n"
                +"\n".join(
                    f"fd: {key}, data: {value!r}"
                    for key, value in self.remaining_data.items())
                + "\n")
            logger.warning("unprocessed data in AssemblingDecoderMixIn")
