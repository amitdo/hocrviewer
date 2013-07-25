import os
import re
from StringIO import StringIO
from functools import wraps

from flask import (Flask, jsonify, abort, request, send_file, current_app,
                   Response, render_template)
from lxml import etree
from wand.image import Image

import search_index

# NOTE: This directory should contain one subdirectory per book, structured as
#       follows:
#         <name>.hocr
#         img/<pagenum>.jpg
#       pagenum should be zero-padded to four, i.e. 0001.<extension>
BOOK_PATH = os.path.join(os.path.expanduser('~'), 'scans')

app = Flask(__name__)


def get_page_fname(bookname, page_idx):
    imgpath = os.path.join(BOOK_PATH, bookname, 'img')
    fname = os.path.join(imgpath,
                         next(x for x in os.listdir(imgpath)
                         if re.match(r"{0:04}\.(png|jpg|jpeg)"
                                     .format(page_idx), x.lower())))
    return fname


@app.route('/')
def index():
    # TODO: Display list of all available books
    return render_template('index.html',
                           books=[x for x in os.listdir(BOOK_PATH)
                                  if not x.startswith('.')])


@app.route('/<bookname>')
def view(bookname):
    # TODO: Display IA Viewer for bookname
    return render_template('viewer.html', bookname=bookname)


@app.route('/api/list')
def list():
    """ Return list of all available books. """
    return jsonify({'books': os.listdir(BOOK_PATH)})


@app.route('/api/reindex')
@app.route('/api/<bookname>/reindex')
def reindex(bookname=None):
    """ Recreate Whoosh index for all or a single book. """
    if bookname and not bookname in os.listdir(BOOK_PATH):
        abort(404)
    if bookname:
        books = [bookname]
    else:
        books = os.listdir(BOOK_PATH)
    for book in books:
        search_index.index_book(book)
    return Response(status=200)


@app.route('/api/<bookname>', methods=['GET'])
def get_book(bookname):
    """ Obtain metadata for book. """
    if not bookname in os.listdir(BOOK_PATH):
        abort(404)
    out_dict = {}
    out_dict['num_pages'] = len(os.listdir(os.path.join(BOOK_PATH, bookname,
                                                        'img')))
    out_dict['title'] = bookname
    # TODO: Open book.hocr, read DC metadata header, turn to json
    return jsonify(out_dict)


@app.route('/api/<bookname>/toc', methods=['GET'])
def get_book_toc(bookname):
    """ Obtain table of contents for book. """
    if not bookname in os.listdir(BOOK_PATH):
        abort(404)
    path = os.path.join(BOOK_PATH, bookname, "{0}.hocr".format(bookname))
    tree = etree.parse(path)
    struc_elems = tree.xpath('//*[@class="ocr_title" or @class="ocr_chapter"'
                             ' or @class="ocr_section"'
                             ' or @class="ocr_subsection"]')
    # NOTE: BookReader TOC is flat at the moment, so we can get away with this:
    output = {'toc': (
        [{'title': "".join(x.itertext()).strip(),
          'pagenum': int(x.xpath('ancestor::div[@class="ocr_page"]')[0]
                         .get('id')[5:])}
         for x in struc_elems])
    }
    return jsonify(output)


@app.route('/api/<bookname>/search/', methods=['GET'])
@app.route('/api/<bookname>/search/<search_term>', methods=['GET'])
def search_book(bookname, search_term=None):
    """ Search for a pattern inside a book. """
    if not bookname in os.listdir(BOOK_PATH):
        abort(404)
    if not search_term:
        abort(400)
    # TODO: Verify that the book has indeed been indexed
    results = search_index.search(search_term, bookname=bookname)
    out_dict = {
        'q': search_term,
        'ia': bookname,
        'matches': [{'text': hit['snippet'],
                     'par': [{
                         'boxes': [
                             {'l': box[0], 't': box[1], 'r': box[2],
                              'b': box[3], 'page': hit['pagenum']}
                             for box in hit['highlights']],
                         'page': hit['pagenum']}]} for hit in results]
    }
    callback = request.args.get('callback', False)
    if callback:
        data = str(jsonify(out_dict).data)
        content = str(callback) + "({0})".format(data)
        mimetype = "application/javascript"
        return current_app.response_class(content, mimetype=mimetype)
    else:
        return jsonify(out_dict)


@app.route('/api/<bookname>/dimensions/')
@app.route('/api/<bookname>/dimensions/<int:page_idx>', methods=['GET'])
def get_dimensions(bookname, page_idx=1):
    """ Obtain width and height for a given page from a book. """
    if not bookname in os.listdir(BOOK_PATH):
        abort(404)
    fname = get_page_fname(bookname, page_idx)
    if not os.path.exists(fname):
        abort(404)
    with Image(filename=fname) as img:
        dimensions = {'width': img.width, 'height': img.height}
    return jsonify(dimensions)


@app.route('/api/<bookname>/img/', methods=['GET'])
@app.route('/api/<bookname>/img/<int:page_idx>', methods=['GET'])
def get_image(bookname, page_idx=1):
    """ Obtain the image of a given page from a book. """
    if not bookname in os.listdir(BOOK_PATH):
        abort(404)
    fname = get_page_fname(bookname, page_idx)
    if not os.path.exists(fname):
        abort(404)
    scale_factor = request.args.get('scale', type=float)
    rotate = request.args.get('rotate', type=int)
    img_io = StringIO()
    with Image(filename=fname) as img:
        print request.args.get('scale', type=int)
        print scale_factor
        if scale_factor:
            print "Scaling!"
            img.resize(width=int(scale_factor*img.width),
                       height=int(scale_factor*img.height))
        if rotate:
            img.rotate(rotate)
        img.save(file=img_io)
        mimetype = img.mimetype
        img_io.seek(0)
    return send_file(img_io, mimetype=mimetype)


@app.route('/api/<bookname>/read/<int:page_idx>', methods=['GET'])
def read_page(bookname, page_idx):
    """ Obtain spoken text of given page. """
    if not bookname in os.listdir(BOOK_PATH):
        abort(404)
    # TODO: Return MP3 with voice that reads the page at page_idx
    raise NotImplementedError


if __name__ == '__main__':
    app.run(debug=True)
