fix: the font used in the toc items is not one of the correct fonts we use, i think it's time new roman or something. 
fix: make the table, figures and code blocks accept a locale: es and en for now, instead of the hard coded TABLA x.y, etc
feature: allow for an arbitrary image in the first page, instead of the hard coded (tho optinal) UJA logo
feature: instead of a fixed master, asingatura etc, change to a more manageable system, that should be instead something like title, subtitle, comment, logo, author, etc (suggestions for better format welcome)
fix: make the overall font size of the document +1 accros the board, since it's too small atm, this includes all titles, susbtitle, headers, normal text, etc EXCEPT HEADERS/FOOTER those two are fine
feature: make it so the objects (tables, figure, code blocks parraghras, titels) can be set to "keep with last item", this way a piece of text can be texturally forced (using a tag or smth) to stay next to the prev item, for example, a code block that is forced to stay below a piece of text, even if this means the code will now break into two blocks. this can be a problem so check edge cases carefully.
fix: make it so the program refuses to create a pdf if any of the tags for an assets (table, figure, code block) doesnt include a descriptros, this way we avoid empty Table x.y with no comment describing it

