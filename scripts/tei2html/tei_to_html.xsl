<?xml version="1.0" encoding="UTF-8"?>
<!-- TibSchol TEI excerpt -> HTML (XSLT 1.0, run through libxslt via lxml).
     Page layout: three clearly separated zones
       1. Document metadata   (what the file is: title, IDs, dates, licence, manuscript)
       2. Creators/investigators (who made it: author, principal, contributors)
       3. Encoded text        (the TEI body itself)
     Styling: Pico.css (vendored in assets/) + assets/tibschol.css -->
<xsl:stylesheet version="1.0"
  xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
  xmlns:tei="http://www.tei-c.org/ns/1.0"
  exclude-result-prefixes="tei">

  <xsl:output method="html" encoding="UTF-8" indent="yes"/>

  <!-- Relative paths, so the page works from the folder it is written to -->
  <xsl:param name="source_href" select="''"/>
  <xsl:param name="stylesheet-href" select="'assets/pico.min.css'"/>
  <xsl:param name="site-css-href" select="'assets/tibschol.css'"/>

  <!-- Group contributor responsibilities by person (one person, several roles) -->
  <xsl:key name="resp-by-name" match="tei:titleStmt/tei:respStmt" use="normalize-space(tei:name)"/>

  <!-- ============ Page shell ============ -->
  <xsl:template match="/">
    <html lang="bo-Latn" data-theme="light">
      <head>
        <meta charset="utf-8"/>
        <meta name="viewport" content="width=device-width, initial-scale=1"/>
        <title>
          <xsl:value-of select="/tei:TEI/tei:teiHeader/tei:fileDesc/tei:titleStmt/tei:title[@type='main']"/>
        </title>
        <link rel="stylesheet" href="{$stylesheet-href}"/>
        <link rel="stylesheet" href="{$site-css-href}"/>
      </head>
      <body>
        <header class="topbar" data-pagefind-ignore="data-pagefind-ignore">
          <!-- Shared with the index and key pages: partials/header.xml -->
          <xsl:copy-of select="document('partials/header.xml')/header/node()"/>
          <details class="menu">
            <summary aria-label="Menu for this text">⋮</summary>
            <div class="menu-list">
              <a href="how-to-read.html">How to read</a>
              <a href="#about">About</a>
              <a href="#credits">Credits</a>
            </div>
          </details>
        </header>

        <main class="container">
          <xsl:apply-templates select="/tei:TEI"/>
        </main>

        <!-- One footer for the page: the repository and institute bar (partials/footer.xml), then the publication line -->
        <xsl:for-each select="/tei:TEI">
          <footer class="site-footer" data-pagefind-ignore="data-pagefind-ignore">
            <div class="site-footer-bar">
              <xsl:copy-of select="document('partials/footer.xml')/footer/div[@class='site-footer-bar']/a"/>
              <p class="colophon-line">
              <xsl:text>Published </xsl:text><xsl:value-of select="tei:teiHeader/tei:fileDesc/tei:publicationStmt/tei:date"/>
              <xsl:text> · </xsl:text><xsl:value-of select="tei:teiHeader/tei:fileDesc/tei:publicationStmt/tei:publisher"/>
              <xsl:text> · </xsl:text><a href="{tei:teiHeader/tei:fileDesc/tei:publicationStmt/tei:availability/tei:licence/@target}">CC BY-SA 4.0</a>
              <xsl:text> · </xsl:text><a href="{$source_href}">TEI XML source</a>
              </p>
              <xsl:copy-of select="document('partials/footer.xml')/footer/div[@class='site-footer-bar']/div"/>
            </div>
            <xsl:copy-of select="document('partials/footer.xml')/footer/script"/>
          </footer>
        </xsl:for-each>
      </body>
    </html>
  </xsl:template>

  <!-- Display name of an entity pointer (#person3933, #work4722, #place6216, #inst4721) -->
  <xsl:template name="entity-name">
    <xsl:param name="ptr"/>
    <xsl:variable name="id">
      <xsl:choose>
        <xsl:when test="contains($ptr, '#')"><xsl:value-of select="substring-after($ptr, '#')"/></xsl:when>
        <xsl:otherwise><xsl:value-of select="concat(substring-before($ptr, ':'), substring-after($ptr, ':'))"/></xsl:otherwise>
      </xsl:choose>
    </xsl:variable>
    <xsl:variable name="el" select="/tei:TEI/tei:standOff//*[@xml:id = $id] | /tei:TEI/tei:teiHeader//tei:msDesc[@xml:id = $id]"/>
    <xsl:choose>
      <xsl:when test="$el/self::tei:person"><xsl:value-of select="$el/tei:persName[@type='main']"/></xsl:when>
      <xsl:when test="$el/self::tei:bibl"><xsl:value-of select="$el/tei:title[@type='main']"/></xsl:when>
      <xsl:when test="$el/self::tei:place"><xsl:value-of select="$el/tei:placeName[not(@type)][1]"/></xsl:when>
      <xsl:when test="$el/self::tei:msDesc"><xsl:value-of select="$el/tei:msIdentifier/tei:msName[not(@xml:lang)]"/></xsl:when>
      <xsl:otherwise><xsl:value-of select="$id"/></xsl:otherwise>
    </xsl:choose>
  </xsl:template>

  <xsl:template match="tei:TEI">
    <xsl:apply-templates select="tei:teiHeader"/>
    <div class="layout">
      <div class="text-col">
        <xsl:apply-templates select="tei:text"/>
      </div>
      <aside class="side" aria-label="Details of the manuscript, work and author">
        <xsl:call-template name="side-panels"/>
      </aside>
    </div>
    <xsl:call-template name="overlays"/>
  </xsl:template>

  <!-- Page head: the title is the first thing a reader sees; the text follows -->
  <xsl:template match="tei:teiHeader">
    <xsl:variable name="fd" select="tei:fileDesc"/>
    <header class="page-head">
      <p class="crumb-small"><a href="index.html">← All TEIs</a></p>
      <h1 id="doc-title"><xsl:value-of select="$fd/tei:titleStmt/tei:title[@type='main']"/></h1>
      <xsl:for-each select="$fd/tei:titleStmt/tei:title[@xml:lang='bo']">
        <p class="tib-title" lang="bo"><xsl:value-of select="."/></p>
      </xsl:for-each>
      <p class="page-sub">
        <xsl:for-each select="$fd/tei:titleStmt/tei:author">
          <xsl:value-of select="."/><xsl:if test="position() != last()">, </xsl:if>
        </xsl:for-each>
        <xsl:text> · </xsl:text>
        <xsl:for-each select="$fd/tei:publicationStmt/tei:idno[@type='TibSchol'][not(. = preceding-sibling::tei:idno[@type='TibSchol'])]">
          <code><xsl:value-of select="."/></code><xsl:if test="position() != last()"><xsl:text>, </xsl:text></xsl:if>
        </xsl:for-each>
      </p>
    </header>
  </xsl:template>

  <!-- One citation: linked short title (or title), then volume, pages and text number -->
  <xsl:template name="bibl-line">
    <xsl:for-each select="tei:ref"><a href="{@target}"><xsl:value-of select="."/></a></xsl:for-each>
    <xsl:for-each select="tei:title"><xsl:value-of select="."/></xsl:for-each>
    <xsl:for-each select="tei:date">
      <xsl:if test="../tei:ref"><xsl:text>, </xsl:text></xsl:if><xsl:value-of select="."/>
    </xsl:for-each>
    <xsl:for-each select="tei:biblScope">
      <xsl:text>, </xsl:text>
      <xsl:choose>
        <xsl:when test="@unit = 'vol'">vol. </xsl:when>
        <xsl:when test="@unit = 'pp'">pp. </xsl:when>
        <xsl:when test="@unit = 'text'">text </xsl:when>
      </xsl:choose>
      <xsl:value-of select="."/>
    </xsl:for-each>
  </xsl:template>

  <!-- A place: name, alternative names, coordinates and feature code (from listPlace) -->
  <xsl:template name="place-value">
    <xsl:param name="ptr"/>
    <!-- $ptr is place:NNNN (prefix form) or #placeNNNN (pointer); both mean the place element with xml:id placeNNNN -->
    <xsl:variable name="pl" select="/tei:TEI/tei:standOff/tei:listPlace/tei:place[@xml:id = substring-after($ptr, '#') or @xml:id = concat('place', substring-after($ptr, ':'))]"/>
    <xsl:choose>
      <xsl:when test="$pl">
        <xsl:for-each select="$pl">
          <span class="place-name"><xsl:value-of select="tei:placeName[not(@type)][1]"/></span>
          <xsl:if test="@type"><span class="place-type"> (<xsl:value-of select="@type"/>)</span></xsl:if>
          <xsl:for-each select="tei:placeName[@type = 'alt']">
            <br/><span class="place-alt"><xsl:value-of select="."/></span>
          </xsl:for-each>
          <xsl:if test="tei:location/tei:geo">
            <br/><span class="place-geo"><xsl:value-of select="tei:location/tei:geo"/></span>
          </xsl:if>
        </xsl:for-each>
      </xsl:when>
      <xsl:otherwise><xsl:value-of select="$ptr"/></xsl:otherwise>
    </xsl:choose>
  </xsl:template>

  <!-- Label for an identifier type in the manuscript panel -->
  <xsl:template name="idno-label">
    <xsl:param name="t"/>
    <xsl:choose>
      <xsl:when test="$t = 'TibSchol'">TibSchol reference</xsl:when>
      <xsl:when test="$t = 'signature'">Signature</xsl:when>
      <xsl:when test="$t = 'drepung'">Drepung no.</xsl:when>
      <xsl:when test="$t = 'set'">Set</xsl:when>
      <xsl:when test="$t = 'volume'">Volume</xsl:when>
      <xsl:when test="$t = 'sbTextNumber'">Text no.</xsl:when>
      <xsl:when test="$t = 'ppKdsb'">Pages</xsl:when>
      <xsl:when test="$t = 'BDRC'">BDRC</xsl:when>
      <xsl:otherwise><xsl:value-of select="$t"/></xsl:otherwise>
    </xsl:choose>
  </xsl:template>

  <!-- One relation line: active, label, passive, with confidence and evidence -->
  <xsl:template name="rel-lines">
    <xsl:param name="rels"/>
    <xsl:variable name="n" select="count($rels)"/>
    <xsl:if test="$n &gt; 0">
    <details class="rels">
      <summary>Relations <span class="count">(<xsl:value-of select="$n"/>)</span></summary>
    <xsl:for-each select="$rels">
      <xsl:sort select="@name"/>
      <xsl:sort select="substring-after(@active, '#')"/>
      <p class="rel">
        <span class="rel-end"><xsl:call-template name="entity-name"><xsl:with-param name="ptr" select="@active"/></xsl:call-template></span>
        <span class="rel-name"><xsl:value-of select="translate(@name, '-', ' ')"/></span>
        <span class="rel-end"><xsl:call-template name="entity-name"><xsl:with-param name="ptr" select="@passive"/></xsl:call-template></span>
        <xsl:if test="@type != 'positive'">
          <span class="rel-conf">(<xsl:value-of select="@type"/>)</span>
        </xsl:if>
        <xsl:for-each select="tei:desc/tei:ptr[1]">
          <xsl:text> </xsl:text>
          <a class="rel-evidence" href="{@target}">evidence</a>
        </xsl:for-each>
      </p>
    </xsl:for-each>
    </details>
    </xsl:if>
  </xsl:template>

  <!-- Side column: one panel per manuscript, the work, and the author.
       Each relation is shown once: instance relations under the manuscript,
       author relations under the author, the other work relations under the work. -->
  <xsl:template name="side-panels">
    <xsl:variable name="aid" select="concat('#person', substring-after(/tei:TEI/tei:teiHeader/tei:fileDesc/tei:titleStmt/tei:author[1]/@ref, ':'))"/>
    <xsl:variable name="wid" select="concat('#work', substring-after(/tei:TEI/tei:teiHeader/tei:fileDesc/tei:sourceDesc/tei:msDesc[1]/tei:msContents/tei:msItem/tei:title[1]/@ref, ':'))"/>
    <xsl:variable name="rels" select="/tei:TEI/tei:standOff/tei:listRelation/tei:relation"/>

    <xsl:for-each select="/tei:TEI/tei:teiHeader/tei:fileDesc/tei:sourceDesc/tei:msDesc">
      <xsl:variable name="mid" select="concat('#', @xml:id)"/>
      <section class="panel panel-ms">
        <p class="panel-label">
          Instance
          <xsl:if test="count(/tei:TEI/tei:teiHeader/tei:fileDesc/tei:sourceDesc/tei:msDesc) &gt; 1">
            <xsl:text> </xsl:text><span class="inst-letter"><xsl:value-of select="substring('ABCDEFGHIJKLMNOP', position(), 1)"/></span>
          </xsl:if>
        </p>
        <h2 class="panel-title"><xsl:value-of select="tei:msIdentifier/tei:msName[not(@xml:lang)]"/></h2>
        <xsl:if test="tei:msIdentifier/tei:msName[@xml:lang='bo']">
          <p class="panel-title-bo" lang="bo"><xsl:value-of select="tei:msIdentifier/tei:msName[@xml:lang='bo']"/></p>
        </xsl:if>
        <dl class="facts">
          <!-- One label per type; repeated values are listed under it -->
          <xsl:if test="tei:msIdentifier/tei:msName[@type = 'alt']">
            <dt>Also known as</dt>
            <dd>
              <xsl:for-each select="tei:msIdentifier/tei:msName[@type = 'alt']">
                <span class="alt-title"><xsl:value-of select="."/></span><xsl:if test="position() != last()"><br/></xsl:if>
              </xsl:for-each>
            </dd>
          </xsl:if>
          <xsl:if test="tei:history/tei:origin/tei:origPlace">
            <dt>Written at</dt>
            <dd>
              <xsl:for-each select="tei:history/tei:origin/tei:origPlace">
                <xsl:call-template name="place-value"><xsl:with-param name="ptr" select="@ref"/></xsl:call-template>
                <xsl:if test="position() != last()"><br/></xsl:if>
              </xsl:for-each>
            </dd>
          </xsl:if>
          <xsl:for-each select="tei:msIdentifier/tei:idno[@type != 'APIS'][not(@type = preceding-sibling::tei:idno/@type)]">
            <dt><xsl:call-template name="idno-label"><xsl:with-param name="t" select="@type"/></xsl:call-template></dt>
            <dd>
              <xsl:for-each select="../tei:idno[@type = current()/@type and @type != 'APIS']">
                <xsl:value-of select="."/><xsl:if test="position() != last()"><br/></xsl:if>
              </xsl:for-each>
            </dd>
          </xsl:for-each>
          <!-- All bibliographic entries of the manuscript under one label: printed edition and Zotero references -->
          <xsl:if test="tei:additional/tei:listBibl/tei:bibl">
            <dt>Citation</dt>
            <dd>
              <xsl:for-each select="tei:additional/tei:listBibl/tei:bibl">
                <span class="cite"><xsl:call-template name="bibl-line"/></span><xsl:if test="position() != last()"><br/></xsl:if>
              </xsl:for-each>
            </dd>
          </xsl:if>
          <!-- People and manuscripts related to this manuscript (from the header) -->
          <xsl:if test="tei:history/tei:origin/tei:persName[@role = 'scribe']">
            <dt>Scribe</dt>
            <dd><xsl:for-each select="tei:history/tei:origin/tei:persName[@role = 'scribe']"><xsl:value-of select="."/><xsl:if test="position() != last()">, </xsl:if></xsl:for-each></dd>
          </xsl:if>
          <xsl:if test="tei:history/tei:origin/tei:persName[@role = 'sponsor']">
            <dt>Sponsor</dt>
            <dd><xsl:for-each select="tei:history/tei:origin/tei:persName[@role = 'sponsor']"><xsl:value-of select="."/><xsl:if test="position() != last()">, </xsl:if></xsl:for-each></dd>
          </xsl:if>
          <xsl:if test="tei:history/tei:provenance/tei:persName[@role = 'owner']">
            <dt>Owner</dt>
            <dd><xsl:for-each select="tei:history/tei:provenance/tei:persName[@role = 'owner']"><xsl:value-of select="."/><xsl:if test="position() != last()">, </xsl:if></xsl:for-each></dd>
          </xsl:if>
          <xsl:if test="tei:physDesc/tei:additions/tei:p/tei:persName[@role = 'annotator']">
            <dt>Annotator</dt>
            <dd><xsl:for-each select="tei:physDesc/tei:additions/tei:p/tei:persName[@role = 'annotator']"><xsl:value-of select="."/><xsl:if test="position() != last()">, </xsl:if></xsl:for-each></dd>
          </xsl:if>
          <xsl:for-each select="tei:history/tei:origin/tei:bibl[@type = 'source']">
            <dt>Source manuscript</dt>
            <dd>
              <xsl:value-of select="tei:name"/>
              <xsl:for-each select="tei:idno[@type = 'TibSchol']"> (<xsl:value-of select="."/>)</xsl:for-each>
            </dd>
          </xsl:for-each>
          <xsl:for-each select="tei:history/tei:origin/tei:bibl[@type = 'isSourceFor']">
            <dt>Is source for</dt>
            <dd>
              <xsl:value-of select="tei:name"/>
              <xsl:for-each select="tei:idno[@type = 'TibSchol']"> (<xsl:value-of select="."/>)</xsl:for-each>
            </dd>
          </xsl:for-each>
          <xsl:for-each select="tei:physDesc/tei:objectDesc/tei:supportDesc/tei:support/tei:dimensions">
            <dt>Dimensions</dt>
            <dd><xsl:value-of select="tei:width"/> × <xsl:value-of select="tei:height"/> cm</dd>
          </xsl:for-each>
          <xsl:for-each select="tei:physDesc/tei:objectDesc/tei:supportDesc/tei:extent">
            <dt>Folios</dt>
            <dd><xsl:value-of select="."/></dd>
          </xsl:for-each>

          <xsl:for-each select="tei:history/tei:provenance[normalize-space(text())]">
            <dt>Provenance</dt>
            <dd><xsl:for-each select="text()"><xsl:value-of select="."/></xsl:for-each></dd>
          </xsl:for-each>
        </dl>
        <xsl:call-template name="rel-lines">
          <xsl:with-param name="rels" select="$rels[(@active = $mid or @passive = $mid) and not(contains(@active, '#place') or contains(@passive, '#place'))]"/>
        </xsl:call-template>
        <!-- Free-text notes: one toggle across the full width of the panel -->
        <xsl:if test="tei:physDesc/tei:objectDesc/tei:supportDesc/tei:support/tei:p or tei:additional/tei:adminInfo/tei:note">
          <details class="long">
            <summary>Notes</summary>
            <xsl:for-each select="tei:physDesc/tei:objectDesc/tei:supportDesc/tei:support/tei:p">
              <p>
                <xsl:for-each select="node()">
                  <xsl:choose>
                    <xsl:when test="self::tei:lb"><br/></xsl:when>
                    <xsl:otherwise><xsl:value-of select="."/></xsl:otherwise>
                  </xsl:choose>
                </xsl:for-each>
              </p>
            </xsl:for-each>
            <xsl:for-each select="tei:additional/tei:adminInfo/tei:note">
              <p><xsl:value-of select="."/></p>
            </xsl:for-each>
          </details>
        </xsl:if>
      </section>
    </xsl:for-each>

    <section class="panel panel-work">
      <p class="panel-label">Work</p>
      <xsl:for-each select="/tei:TEI/tei:standOff/tei:listBibl/tei:bibl[@xml:id = substring($wid, 2)]">
        <h2 class="panel-title"><xsl:value-of select="tei:title[@type='main']"/></h2>
        <xsl:for-each select="tei:title[@xml:lang='bo']">
          <p class="panel-title-bo" lang="bo"><xsl:value-of select="."/></p>
        </xsl:for-each>
        <xsl:if test="tei:title[@type='alt']">
          <dl class="facts">
            <dt>Also known as</dt>
            <dd>
              <xsl:for-each select="tei:title[@type='alt']">
                <span class="alt-title"><xsl:value-of select="."/></span><xsl:if test="position() != last()"><br/></xsl:if>
              </xsl:for-each>
            </dd>
          </dl>
        </xsl:if>
        <dl class="facts">
          <xsl:if test="tei:date">
            <dt>Composition</dt>
            <dd><xsl:value-of select="tei:date"/></dd>
          </xsl:if>
          <xsl:if test="tei:textLang">
            <dt>Language</dt>
            <dd><xsl:if test="tei:textLang/@mainLang = 'bo'">Tibetan</xsl:if></dd>
          </xsl:if>
          <xsl:if test="tei:note[@type='isExtant']">
            <dt>Extant</dt>
            <dd><xsl:value-of select="tei:note[@type='isExtant']"/></dd>
          </xsl:if>
        </dl>
        <xsl:if test="tei:respStmt[tei:resp = 'translator' or tei:resp = 'prompter'] or tei:relatedItem">
          <dl class="facts">
            <xsl:if test="tei:respStmt[tei:resp = 'translator']">
              <dt>Translator</dt>
              <dd><xsl:for-each select="tei:respStmt[tei:resp = 'translator']"><xsl:value-of select="tei:name"/><xsl:if test="position() != last()">, </xsl:if></xsl:for-each></dd>
            </xsl:if>
            <xsl:if test="tei:respStmt[tei:resp = 'prompter']">
              <dt>Prompter</dt>
              <dd><xsl:for-each select="tei:respStmt[tei:resp = 'prompter']"><xsl:value-of select="tei:name"/><xsl:if test="position() != last()">, </xsl:if></xsl:for-each></dd>
            </xsl:if>
            <xsl:for-each select="tei:relatedItem">
              <xsl:if test="@type = 'biographyOf' and not(preceding-sibling::tei:relatedItem[@type = 'biographyOf'])">
                <dt>Biography of</dt>
                <dd><xsl:for-each select="../tei:relatedItem[@type = 'biographyOf']"><xsl:call-template name="entity-name"><xsl:with-param name="ptr" select="@target"/></xsl:call-template><xsl:if test="position() != last()"><br/></xsl:if></xsl:for-each></dd>
              </xsl:if>
              <xsl:if test="@type = 'recordsTeachingOf' and not(preceding-sibling::tei:relatedItem[@type = 'recordsTeachingOf'])">
                <dt>Records the teaching of</dt>
                <dd><xsl:for-each select="../tei:relatedItem[@type = 'recordsTeachingOf']"><xsl:call-template name="entity-name"><xsl:with-param name="ptr" select="@target"/></xsl:call-template><xsl:if test="position() != last()"><br/></xsl:if></xsl:for-each></dd>
              </xsl:if>
              <xsl:if test="@type = 'addressedTo' and not(preceding-sibling::tei:relatedItem[@type = 'addressedTo'])">
                <dt>Addressed to</dt>
                <dd><xsl:for-each select="../tei:relatedItem[@type = 'addressedTo']"><xsl:call-template name="entity-name"><xsl:with-param name="ptr" select="@target"/></xsl:call-template><xsl:if test="position() != last()"><br/></xsl:if></xsl:for-each></dd>
              </xsl:if>
              <xsl:if test="@type = 'commentaryOn' and not(preceding-sibling::tei:relatedItem[@type = 'commentaryOn'])">
                <dt>Commentary on</dt>
                <dd><xsl:for-each select="../tei:relatedItem[@type = 'commentaryOn']"><xsl:call-template name="entity-name"><xsl:with-param name="ptr" select="@target"/></xsl:call-template><xsl:if test="position() != last()"><br/></xsl:if></xsl:for-each></dd>
              </xsl:if>
              <xsl:if test="@type = 'citesWork' and not(preceding-sibling::tei:relatedItem[@type = 'citesWork'])">
                <dt>Cites</dt>
                <dd><xsl:for-each select="../tei:relatedItem[@type = 'citesWork']"><xsl:call-template name="entity-name"><xsl:with-param name="ptr" select="@target"/></xsl:call-template><xsl:if test="position() != last()"><br/></xsl:if></xsl:for-each></dd>
              </xsl:if>
            </xsl:for-each>
          </dl>
        </xsl:if>
        <xsl:if test="$rels[@name = 'composed-at' and @active = $wid]">
          <dl class="facts"><dt>Composed at</dt><dd>
            <xsl:for-each select="$rels[@name = 'composed-at' and @active = $wid]">
              <xsl:call-template name="place-value"><xsl:with-param name="ptr" select="@passive"/></xsl:call-template>
              <xsl:if test="position() != last()"><br/></xsl:if>
            </xsl:for-each>
          </dd></dl>
        </xsl:if>
        <xsl:if test="$rels[@name = 'taught-at' and @active = $wid]">
          <dl class="facts"><dt>Taught at</dt><dd>
            <xsl:for-each select="$rels[@name = 'taught-at' and @active = $wid]">
              <xsl:call-template name="place-value"><xsl:with-param name="ptr" select="@passive"/></xsl:call-template>
              <xsl:if test="position() != last()"><br/></xsl:if>
            </xsl:for-each>
          </dd></dl>
        </xsl:if>
        <xsl:call-template name="rel-lines">
          <xsl:with-param name="rels" select="$rels[(@active = $wid or @passive = $wid) and not(@active = $aid or @passive = $aid) and not(contains(@active, '#place') or contains(@passive, '#place'))]"/>
        </xsl:call-template>
        <xsl:if test="tei:note[@type='comment']">
          <details class="long">
            <summary>Notes</summary>
            <p><xsl:value-of select="tei:note[@type='comment']"/></p>
          </details>
        </xsl:if>
      </xsl:for-each>
    </section>

    <section class="panel panel-author">
      <p class="panel-label">Author</p>
      <xsl:choose>
        <xsl:when test="/tei:TEI/tei:standOff/tei:listPerson/tei:person[@xml:id = substring($aid, 2)]">
          <xsl:for-each select="/tei:TEI/tei:standOff/tei:listPerson/tei:person[@xml:id = substring($aid, 2)]">
            <h2 class="panel-title"><xsl:value-of select="tei:persName[@type='main']"/></h2>
            <xsl:for-each select="tei:persName[@xml:lang='bo']">
              <p class="panel-title-bo" lang="bo"><xsl:value-of select="."/></p>
            </xsl:for-each>
            <dl class="facts">
              <xsl:if test="tei:persName[@type = 'alt']">
                <dt>Also known as</dt>
                <dd>
                  <xsl:for-each select="tei:persName[@type = 'alt']">
                    <span class="alt-title"><xsl:value-of select="."/></span><xsl:if test="position() != last()"><br/></xsl:if>
                  </xsl:for-each>
                </dd>
              </xsl:if>
              <xsl:if test="$rels[@name = 'active-at' and @active = $aid]">
                <dt>Active at</dt>
                <dd>
                  <xsl:for-each select="$rels[@name = 'active-at' and @active = $aid]">
                    <xsl:call-template name="place-value"><xsl:with-param name="ptr" select="@passive"/></xsl:call-template>
                    <xsl:if test="position() != last()"><br/></xsl:if>
                  </xsl:for-each>
                </dd>
              </xsl:if>
              <xsl:if test="tei:birth or tei:death">
                <dt>Dates</dt>
                <dd><xsl:value-of select="tei:birth"/><xsl:if test="tei:birth and tei:death"> – </xsl:if><xsl:value-of select="tei:death"/></dd>
              </xsl:if>
              <xsl:if test="tei:nationality">
                <dt>Nationality</dt>
                <dd><xsl:value-of select="tei:nationality"/></dd>
              </xsl:if>
              <xsl:if test="tei:sex">
                <dt>Gender</dt>
                <dd><xsl:if test="tei:sex/@value = 'M'">Male</xsl:if><xsl:if test="tei:sex/@value = 'F'">Female</xsl:if></dd>
              </xsl:if>
              <xsl:for-each select="tei:idno[@type = 'BDRC']">
                <dt>BDRC</dt>
                <dd><xsl:value-of select="."/></dd>
              </xsl:for-each>
            </dl>

            <xsl:call-template name="rel-lines">
              <xsl:with-param name="rels" select="$rels[(@active = $aid or @passive = $aid) and not(contains(@active, '#place') or contains(@passive, '#place'))]"/>
            </xsl:call-template>
            <xsl:if test="tei:note[@type='comment']">
              <details class="long">
                <summary>Notes</summary>
                <p><xsl:value-of select="tei:note[@type='comment']"/></p>
              </details>
            </xsl:if>
          </xsl:for-each>
        </xsl:when>
        <xsl:otherwise>
          <h2 class="panel-title"><xsl:value-of select="/tei:TEI/tei:teiHeader/tei:fileDesc/tei:titleStmt/tei:author[1]"/></h2>
        </xsl:otherwise>
      </xsl:choose>
    </section>
  </xsl:template>

  <!-- 2. Project team: the people who prepared this TEI (not the author of the work) -->
  <xsl:key name="resp-by-role" match="tei:titleStmt/tei:respStmt" use="normalize-space(tei:resp)"/>

  <!-- Overlays for this text only: About and Credits. Opened from the ⋮ menu (CSS :target, no script). -->
  <xsl:template name="overlays">
    <xsl:variable name="fd" select="tei:teiHeader/tei:fileDesc"/>
    <section id="about" class="overlay" aria-labelledby="about-h">
      <div class="overlay-box">
        <a class="overlay-close" href="#" aria-label="Close">×</a>
        <h2 id="about-h">About this text</h2>
        <xsl:for-each select="tei:teiHeader/tei:encodingDesc/tei:projectDesc/tei:p">
          <p class="about-text"><xsl:value-of select="normalize-space(.)"/></p>
        </xsl:for-each>
        <dl class="facts">
          <dt>Publisher</dt><dd><xsl:value-of select="$fd/tei:publicationStmt/tei:publisher"/></dd>
          <dt>Published</dt><dd><xsl:value-of select="$fd/tei:publicationStmt/tei:date"/></dd>
          <dt>Edition</dt><dd><xsl:value-of select="$fd/tei:editionStmt/tei:edition"/></dd>
          <dt>Licence</dt>
          <dd><a href="{$fd/tei:publicationStmt/tei:availability/tei:licence/@target}">Creative Commons Attribution-ShareAlike 4.0 International (CC BY-SA 4.0)</a></dd>
          <dt>Funder</dt>
          <dd>
            <xsl:for-each select="$fd/tei:titleStmt/tei:funder/tei:name">
              <xsl:choose>
                <xsl:when test="starts-with(@ref, 'http')"><a href="{@ref}"><xsl:value-of select="normalize-space(.)"/></a></xsl:when>
                <xsl:otherwise><xsl:value-of select="normalize-space(.)"/></xsl:otherwise>
              </xsl:choose>
            </xsl:for-each>
          </dd>
          <xsl:for-each select="$fd/tei:publicationStmt/tei:idno[@type != 'TibSchol']">
            <dt><xsl:value-of select="@type"/></dt>
            <dd><xsl:value-of select="."/></dd>
          </xsl:for-each>
        </dl>
      </div>
    </section>

    <section id="credits" class="overlay" aria-labelledby="credits-h">
      <div class="overlay-box">
        <a class="overlay-close" href="#" aria-label="Close">×</a>
        <h2 id="credits-h">Credits</h2>
        <dl class="credit-list">
          <xsl:if test="$fd/tei:titleStmt/tei:principal/tei:name">
            <dt>Principal investigator</dt>
            <dd>
              <xsl:for-each select="$fd/tei:titleStmt/tei:principal/tei:name">
                <xsl:value-of select="normalize-space(.)"/><xsl:if test="position() != last()"><xsl:text>, </xsl:text></xsl:if>
              </xsl:for-each>
            </dd>
          </xsl:if>
          <xsl:for-each select="$fd/tei:titleStmt/tei:respStmt[generate-id()=generate-id(key('resp-by-role', normalize-space(tei:resp))[1])]">
            <dt><xsl:value-of select="normalize-space(tei:resp)"/></dt>
            <dd>
              <xsl:for-each select="key('resp-by-role', normalize-space(tei:resp))">
                <xsl:value-of select="normalize-space(tei:name)"/>
                <xsl:if test="position() != last()"><xsl:text>, </xsl:text></xsl:if>
              </xsl:for-each>
            </dd>
          </xsl:for-each>
        </dl>
      </div>
    </section>
  </xsl:template>

  <!-- ============ 3: the encoded text ============ -->
  <xsl:template match="tei:text">
    <section class="zone zone-data" aria-label="Encoded text">
      <p class="zone-label">Encoded text</p>
      <div class="tib-text">
        <xsl:apply-templates/>
      </div>
    </section>
  </xsl:template>

  <xsl:template match="tei:body">
    <div class="body"><xsl:apply-templates/></div>
  </xsl:template>

  <xsl:template match="tei:ab">
    <div class="ab">
      <xsl:if test="@type"><xsl:attribute name="class">ab <xsl:value-of select="@type"/></xsl:attribute></xsl:if>
      <xsl:apply-templates/>
    </div>
  </xsl:template>

  <xsl:template match="tei:seg">
    <div class="seg" id="{@xml:id}" data-status="{@status}">
      <xsl:apply-templates/>
    </div>
  </xsl:template>

  <xsl:template match="tei:milestone">
    <xsl:if test="@n">
      <div class="milestone"><xsl:value-of select="@n"/></div>
    </xsl:if>
  </xsl:template>

  <xsl:template match="tei:lg">
    <div class="lg"><xsl:apply-templates/></div>
  </xsl:template>

  <xsl:template match="tei:l">
    <div class="l"><xsl:apply-templates/></div>
  </xsl:template>

  <!-- Paragraphs and text divisions: blocks, as in the local prototype.
       Rendered as div so that block content inside a paragraph stays valid HTML. -->
  <xsl:template match="tei:p">
    <div class="p"><xsl:apply-templates/></div>
  </xsl:template>

  <xsl:template match="tei:div">
    <div class="div" data-type="{@type}"><xsl:apply-templates/></div>
  </xsl:template>

  <!-- Page and line breaks: the number is shown via CSS ::before -->
  <xsl:template match="tei:pb">
    <xsl:variable name="inst"><xsl:if test="@edRef"><xsl:call-template name="inst-label"><xsl:with-param name="ref" select="@edRef"/></xsl:call-template></xsl:if></xsl:variable>
    <span class="pb" data-n="{@n}" data-inst="{$inst}"></span>
  </xsl:template>

  <xsl:template match="tei:lb">
    <xsl:variable name="inst"><xsl:if test="@edRef"><xsl:call-template name="inst-label"><xsl:with-param name="ref" select="@edRef"/></xsl:call-template></xsl:if></xsl:variable>
    <span class="lb" data-n="{@n}" data-inst="{$inst}"></span>
  </xsl:template>

  <!-- Letter (A, B, ...) of the instance a pointer such as inst:4721 refers to,
       i.e. its position among the msDesc elements of the file -->
  <!-- Only when the file has more than one manuscript; a single manuscript needs no letter -->
  <xsl:template name="inst-label">
    <xsl:param name="ref"/>
    <xsl:variable name="id" select="concat('inst', substring-after(normalize-space($ref), ':'))"/>
    <xsl:variable name="ms" select="/tei:TEI/tei:teiHeader/tei:fileDesc/tei:sourceDesc/tei:msDesc[@xml:id = $id]"/>
    <xsl:if test="count(/tei:TEI/tei:teiHeader/tei:fileDesc/tei:sourceDesc/tei:msDesc) &gt; 1">
      <xsl:value-of select="substring('ABCDEFGHIJKLMNOP', count($ms/preceding-sibling::tei:msDesc) + 1, 1)"/>
    </xsl:if>
  </xsl:template>

  <!-- Variant readings: the lemma is shown; each other reading is listed with its instance -->
  <!-- Without a lemma, the first reading is shown in the text and the others are listed; the case is reported -->
  <xsl:template match="tei:app">
    <xsl:variable name="main" select="(tei:lem)[1] | (tei:rdg[not(../tei:lem)])[1]"/>
    <span class="app">
      <xsl:apply-templates select="$main"/>
      <sup class="variants"><xsl:for-each select="tei:rdg[generate-id() != generate-id($main)]">
        <span class="rdg"><xsl:call-template name="inst-label"><xsl:with-param name="ref" select="substring-before(concat(normalize-space(@wit), ' '), ' ')"/></xsl:call-template>: <xsl:apply-templates/></span>
      </xsl:for-each></sup>
    </span>
    <xsl:if test="not(tei:lem)">
      <xsl:message>TIBREPORT|app-no-lemma|<xsl:value-of select="ancestor::tei:seg[1]/@xml:id"/>|<xsl:value-of select="count(tei:rdg)"/> readings, first shown</xsl:message>
    </xsl:if>
  </xsl:template>

  <xsl:template match="tei:lem">
    <xsl:apply-templates/>
  </xsl:template>

  <xsl:template match="tei:expan">
    <xsl:apply-templates/>
  </xsl:template>

  <!-- Choice: show the regularised/corrected form; the original (or uncorrected) form goes into a tooltip.
       Without a reg/orig or corr/sic pair, all children are shown as before. -->
  <!-- Choice, matched by role rather than by order:
       the displayed form is reg or corr; the other form (orig or sic) goes into the tooltip.
       Without a reg/corr, both forms are shown as "unresolved" (dotted underline, tooltip lists them)
       and the case is written to the build report. -->
  <xsl:template match="tei:choice">
    <xsl:variable name="shown" select="(tei:reg | tei:corr)[1]"/>
    <xsl:variable name="other" select="(tei:orig | tei:sic)[1]"/>
    <xsl:choose>
      <xsl:when test="$shown and $other">
        <span class="choice">
          <xsl:attribute name="title">
            <xsl:choose>
              <xsl:when test="$other/self::tei:orig">original: </xsl:when>
              <xsl:otherwise>sic: </xsl:otherwise>
            </xsl:choose>
            <xsl:value-of select="normalize-space($other)"/>
          </xsl:attribute>
          <xsl:apply-templates select="$shown/node()"/>
        </span>
      </xsl:when>
      <xsl:when test="$shown">
        <span class="choice"><xsl:apply-templates select="$shown/node()"/></span>
      </xsl:when>
      <xsl:otherwise>
        <span class="choice-unresolved">
          <xsl:attribute name="title">
            <xsl:for-each select="*">
              <xsl:if test="position() &gt; 1">; </xsl:if>
              <xsl:value-of select="local-name()"/>: <xsl:value-of select="normalize-space(.)"/>
            </xsl:for-each>
          </xsl:attribute>
          <xsl:apply-templates/>
        </span>
        <xsl:message>TIBREPORT|choice-unresolved|<xsl:value-of select="ancestor::tei:seg[1]/@xml:id"/>|<xsl:for-each select="*"><xsl:if test="position() &gt; 1"> / </xsl:if><xsl:value-of select="local-name()"/>=<xsl:value-of select="normalize-space(.)"/></xsl:for-each></xsl:message>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:template>

  <!-- Parts of a choice or variant: shown as their text (the choice template decides what is displayed) -->
  <xsl:template match="tei:reg | tei:corr | tei:orig | tei:sic | tei:rdg">
    <xsl:apply-templates/>
  </xsl:template>

  <xsl:template match="tei:gap">
    <span class="gap" title="{@reason}">[…]</span>
  </xsl:template>

  <!-- Named entity references: keep the database id for later cross-linking -->
  <xsl:template match="tei:rs">
    <span class="rs rs-{@type}" data-ref="{@ref}" title="{@type}: {@ref}">
      <xsl:apply-templates/>
    </span>
  </xsl:template>

  <!-- Glosses: the text stays in the line, marked with ‹ › -->
  <xsl:template match="tei:note[@type='gloss']">
    <span class="gloss"> ‹<xsl:apply-templates/>› </span>
  </xsl:template>

  <!-- All other notes (editorial, translation, comment, ...): collapsed by default, like editorial notes.
       The summary always names the note type; a note without a type is labelled "note". -->
  <xsl:template match="tei:note[not(@type='gloss')]">
    <xsl:if test="not(@type)">
      <xsl:message>TIBREPORT|note-untyped|<xsl:value-of select="ancestor::tei:seg[1]/@xml:id"/>|</xsl:message>
    </xsl:if>
    <details class="note">
      <summary>
        <xsl:choose>
          <xsl:when test="@type"><xsl:value-of select="@type"/></xsl:when>
          <xsl:otherwise>note</xsl:otherwise>
        </xsl:choose>
      </summary>
      <span class="note-body"><xsl:apply-templates/></span>
    </details>
  </xsl:template>

  <!-- Quotations: always a block quote; the citation line is added only when the source is given -->
  <xsl:template match="tei:quote">
    <div class="quote">
      <blockquote><xsl:apply-templates/></blockquote>
      <xsl:if test="@source">
        <div class="quote-cite">
          <xsl:call-template name="entity-name"><xsl:with-param name="ptr" select="@source"/></xsl:call-template>
          <xsl:if test="@n">, <xsl:value-of select="@n"/></xsl:if>
        </div>
      </xsl:if>
    </div>
  </xsl:template>

  <xsl:template match="tei:mentioned">
    <em><xsl:apply-templates/></em>
  </xsl:template>

  <!-- Foreign-language words: italic, language in the tooltip -->
  <xsl:template match="tei:foreign">
    <span class="foreign" title="{@xml:lang}"><xsl:apply-templates/></span>
  </xsl:template>

  <!-- Unclear reading: brackets are added in CSS -->
  <xsl:template match="tei:unclear">
    <span class="unclear"><xsl:apply-templates/></span>
  </xsl:template>

  <!-- Fallback: keep text, mark unknown elements so they are visible while developing -->
  <xsl:template match="*">
    <xsl:if test="ancestor::tei:text">
      <xsl:message>TIBREPORT|unhandled-element|<xsl:value-of select="ancestor::tei:seg[1]/@xml:id"/>|<xsl:value-of select="local-name()"/></xsl:message>
    </xsl:if>
    <span class="unknown tei-{local-name()}"><xsl:apply-templates/></span>
  </xsl:template>

  <!-- Prefix definitions and similar non-display content -->
  <xsl:template match="tei:prefixDef | tei:tagsDecl | tei:listPrefixDef"/>

</xsl:stylesheet>
